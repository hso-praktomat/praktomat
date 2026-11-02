import os
from os.path import abspath, exists
import time
import subprocess
import string
import psutil
import uuid

from copy import deepcopy
from contextlib import ExitStack
from collections.abc import Mapping, Sequence
from typing import NamedTuple, TypedDict

from django.conf import settings

# found at http://stackoverflow.com/questions/1230669/subprocess-deleting-child-processes-in-windows
# should work for linux, too
# TODO: should kill child or grandchild processes, but didn't if they are running as other user;
#       wherefor it is necessary to use "ulimit -t 60" command in shell-scripts called by praktomat checkers:
#       forcing script exit with error after 60 seconds
def kill_proc_tree(pid: int, including_parent: bool = False) -> None:
	parent = psutil.Process(pid)
	children = parent.children(recursive=True)
	for child in children:
		child.kill()
	psutil.wait_procs(children, timeout=5)
	if including_parent:
		parent.kill()
		parent.wait(5)

class ExecutionResult(NamedTuple):
    output: str
    error: bytes | None
    exitcode: int
    timed_out: bool
    oom_ed: bool


class DockerVolume(TypedDict):
    container: str
    dir: str
    volume: str


def execute_arglist(
    args: list[str],
    working_directory: str,
    environment_variables: Mapping[str, str] | None = None,
    timeout: float | None = None,
    maxmem: int | None = None,
    fileseeklimit: int | None = None,
    extradirs: Sequence[str] = (),
    unsafe: bool = False,
    error_to_output: bool = True,
    filenumberlimit: int = 128,
    mount_extra_directories: bool = False,
) -> ExecutionResult:
    """Execute an argument list and return an immutable five-item ExecutionResult."""
    assert isinstance(args, list)

    environment_variables = environment_variables if environment_variables is not None else {}
    environment = os.environ.copy()
    environment.update(environment_variables)
    fileseeklimitbytes = fileseeklimit * 1024 if fileseeklimit is not None else None
    container_name: str | None = None
    volumes: list[DockerVolume] = []
    use_tester = not unsafe and settings.USEPRAKTOMATTESTER

    sudo_prefix = ["sudo", "-E", "-u", "tester"]

    # Limit the size of files created during execution.
    # In newer versions, R requires more to be started
    # (see comment in RscriptChecker.py),
    # even if it does not use it.
    prlimit_prefix = ['prlimit', '--nofile=%d' % filenumberlimit]
    if fileseeklimitbytes is not None:
        prlimit_prefix += ['--fsize=%d' % fileseeklimitbytes]

    command = prlimit_prefix

    if unsafe:
        pass
    elif use_tester:
        #command = sudo_prefix
        #fixed: 22.11.2016, Robert Hartmann , H-BRS
        command += deepcopy(sudo_prefix)
    elif settings.USESAFEDOCKER:
        docker_ulimits = [f"nofile={filenumberlimit}"]
        if fileseeklimitbytes is not None:
            docker_ulimits += [f"fsize={fileseeklimitbytes}"]

        safe_docker_cmd, container_name, volumes = safe_docker(
            environment_variables=environment_variables,
            extra_dirs=extradirs,
            maxmem=maxmem,
            ulimits=docker_ulimits,
            working_directory=abspath(working_directory),
            mount_extra_directories=mount_extra_directories,
        )
        command += safe_docker_cmd

    command += args[:]

    # TODO: Dont even read in output longer than fileseeklimit. This might be most conveniently done by supplying a file like object instead of PIPE

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if error_to_output else subprocess.PIPE,
            cwd=working_directory,
            env=environment,
            start_new_session=True)

        timed_out = False
        oom_ed = False
        try:
            [output, error] = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            term_cmd = ["pkill", "-TERM", "-s", str(process.pid)]
            int_cmd  = ["pkill","-INT","-s",str(process.pid)]
            hup_cmd  = ["pkill","-HUP","-s",str(process.pid)]
            kill_cmd = ["pkill", "-KILL", "-s", str(process.pid)]
            if use_tester:
                term_cmd = sudo_prefix + term_cmd
                int_cmd = sudo_prefix + int_cmd
                hup_cmd = sudo_prefix + hup_cmd
                kill_cmd = sudo_prefix + kill_cmd
            if container_name is not None:
                docker_kill_cmd = ["sudo", "docker", "kill", container_name]
                subprocess.call(docker_kill_cmd)
            if container_name is None or process.poll() is None:
                # Fall back to process cleanup if killing the container did not help.
                subprocess.call(term_cmd)
                time.sleep(5)
                subprocess.call(int_cmd)
                time.sleep(9)
                subprocess.call(hup_cmd)
                time.sleep(5)
                subprocess.call(kill_cmd)
                time.sleep(5)
                if process.poll() is None:
                    kill_proc_tree(pid=process.pid)
                    time.sleep(5)
                    process.kill()
            [output, error] = process.communicate()

        # These exit codes originate from the original safe-docker script.
        if container_name is not None and not timed_out and process.returncode in (255, 137):
            oom_ed = True

        assert process.returncode is not None
        return ExecutionResult(output.decode('utf-8'), error, process.returncode, timed_out, oom_ed)
    finally:
        if container_name is not None:
            safe_docker_cleanup(volumes)


def _requires_task_id(template: string.Template) -> bool:
    return any(
        (match.group('named') or match.group('braced')) == 'TASK_ID_CUSTOM'
        for match in template.pattern.finditer(template.template)
    )


def safe_docker(
    environment_variables: Mapping[str, str],
    extra_dirs: Sequence[str],
    maxmem: int | None,
    ulimits: list[str],
    working_directory: str,
    mount_extra_directories: bool = False,
) -> tuple[list[str], str, list[DockerVolume]]:
    with ExitStack() as rollback:
        result = _safe_docker(
            environment_variables, extra_dirs, maxmem, ulimits,
            working_directory, mount_extra_directories, rollback,
        )
        rollback.pop_all()
        return result


def _safe_docker(
    environment_variables: Mapping[str, str],
    extra_dirs: Sequence[str],
    maxmem: int | None,
    ulimits: list[str],
    working_directory: str,
    mount_extra_directories: bool,
    rollback: ExitStack,
) -> tuple[list[str], str, list[DockerVolume]]:
    cmd = ["sudo", "docker", "run", "--rm", "--sig-proxy",
        "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", "/home"]

    uid = os.getuid()
    gid = os.getgid()

    if ":" in working_directory:
        raise Exception("working directory contains a ':'")
    for d in extra_dirs:
        if ":" in d:
            raise Exception(f"extra directory 'f{d}' contains a ':'")

    volumes: list[DockerVolume] = []
    def add_dir(
        path: str, read_only: bool, volumes: list[DockerVolume]
    ) -> list[str]:
        ro_flag = ""
        if read_only:
            ro_flag = ":ro"

        if not exists("/.dockerenv"):
            # Praktomat is not running in a dockerized environment
            return [f"--volume={path}:{path}{ro_flag}"]

        # Praktomat is running in a dockerized environment

        if not path.endswith("/"):
            # Add trailing slash to path
            path += "/"

        volume_name = f"tmp-{uuid.uuid4()}"
        helper_name = f"tmp-helper-{uuid.uuid4()}"
        subprocess.run(
            ["sudo", "docker", "volume", "create", volume_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            check=True,
        )
        rollback.callback(
            subprocess.run, ["sudo", "docker", "volume", "rm", volume_name],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=True,
        )
        subprocess.run(
            ["sudo", "docker", "run", "-d", f"--volume={volume_name}:{path}", "--name",
                helper_name, "busybox", "sleep", "infinity"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            check=True,
        )
        rollback.callback(
            subprocess.run, ["sudo", "docker", "container", "rm", "-f", helper_name],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=True,
        )
        subprocess.run(
            ["sudo", "docker", "cp", f"{path}.", f"{helper_name}:{path}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            check=True,
        )
        subprocess.run(
            ["sudo", "docker", "exec", helper_name, "chown", "-R", f"{uid}:{gid}", path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            check=True,
        )
        subprocess.run(
            ["sudo", "docker", "kill", helper_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            check=True,
        )
        volumes.append({"container": helper_name, "dir": path, "volume": volume_name})
        return [f"--volume={volume_name}:{path}{ro_flag}"]

    if settings.DOCKER_CONTAINER_HOST_NET:
        # Allow accessing the host network
        cmd += ["--net=host"]
    else:
        cmd += ["--net=none"]

    if not settings.DOCKER_CONTAINER_WRITABLE:
        cmd += ["--read-only"]

    if maxmem is None:
        maxmem = 1024
    cmd += [f"--memory={maxmem}m"]
    for ulimit in ulimits:
        cmd += [f"--ulimit={ulimit}"]
    
    if settings.DOCKER_UID_MOD:
        cmd += [f"--user={uid}:{gid}"]

    for d in extra_dirs:
        cmd += add_dir(d, True, volumes)

    if settings.DOCKER_CONTAINER_EXTERNAL_DIR is not None:
        external_dir = None
        tmpl = string.Template(settings.DOCKER_CONTAINER_EXTERNAL_DIR)
        var_id = "TASK_ID_CUSTOM"
        requires_task_id_custom = _requires_task_id(tmpl)
        if requires_task_id_custom:
            task_id_custom = environment_variables.get(var_id)
            if task_id_custom is not None and task_id_custom != "":
                external_dir = string.Template(settings.DOCKER_CONTAINER_EXTERNAL_DIR).substitute(TASK_ID_CUSTOM=task_id_custom)
        else:
            external_dir = settings.DOCKER_CONTAINER_EXTERNAL_DIR
        if external_dir is not None:
            cmd += [f"--volume={external_dir}:/external:ro"]
    

    if mount_extra_directories:
        extra_external_dirs = [
            settings.DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_1,
            settings.DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_2,
            settings.DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_3,
            settings.DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_4,
            settings.DOCKER_CONTAINER_EXTERNAL_EXTRA_DIR_5,
        ]

        for external_dir in extra_external_dirs:
            if external_dir:
                tmpl = string.Template(external_dir)
                var_id = "TASK_ID_CUSTOM"

                if _requires_task_id(tmpl):
                    task_id_custom = environment_variables.get(var_id)
                    if task_id_custom:
                        external_dir = tmpl.substitute(TASK_ID_CUSTOM=task_id_custom)
                    else:
                        continue

                cmd += [f"--volume={external_dir}"]


    cmd += add_dir(working_directory, False, volumes)
    cmd += [f"--workdir={working_directory}"]

    container_name = f"secure-tmp-{uuid.uuid4()}"
    cmd += ["--name", container_name]
    cmd += [settings.DOCKER_IMAGE_NAME]

    # add environment
    cmd += ["env"]
    for k, v in environment_variables.items():
        cmd += ["%s=%s" % (k, v)]

    return cmd, container_name, volumes


def safe_docker_cleanup(volumes: Sequence[DockerVolume]) -> None:
    with ExitStack() as cleanup:
        for volume in volumes:
            cleanup.callback(
                subprocess.run, ["sudo", "docker", "volume", "rm", volume["volume"]],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=True,
            )
            cleanup.callback(
                subprocess.run, ["sudo", "docker", "container", "rm", volume["container"]],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=True,
            )
        if not settings.DOCKER_DISCARD_ARTEFACTS:
            for volume in volumes:
                subprocess.run(
                    ["sudo", "docker", "cp", f"{volume['container']}:{volume['dir']}.", volume["dir"]],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=True,
                )
