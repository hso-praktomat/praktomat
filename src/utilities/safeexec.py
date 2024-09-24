import os
from os.path import *
import time
import subprocess
import signal
import string
import resource
import psutil
import uuid

from copy import deepcopy

from django.conf import settings

# found at http://stackoverflow.com/questions/1230669/subprocess-deleting-child-processes-in-windows
# should work for linux, too
# TODO: should kill child or grandchild processes, but didn't if they are running as other user;
#       wherefor it is necessary to use "ulimit -t 60" command in shell-scripts called by praktomat checkers:
#       forcing script exit with error after 60 seconds
def kill_proc_tree(pid, including_parent=False):
	parent = psutil.Process(pid)
	# just for debugging in development vm
        #f = open('workfile.rh', 'a', 0)
	f = None
	if f is not None:
		f.write("\n inside kill_proc_tree : " +str(parent.pid()) +" :"  +str(parent.cmdline())+"\n")

	children = parent.children(recursive=True)
	for child in children:
		if f is not None:
			f.write("\n try kill: "+str(child.pid())+":"+str(child.cmdline())+"\n")
		child.kill()
		if f is not None:
			f.write("\n kill returned\n ")
	psutil.wait_procs(children, timeout=5)
	if including_parent:
		parent.kill()
		parent.wait(5)

def execute_arglist(args, working_directory, environment_variables={}, timeout=None, maxmem=None, fileseeklimit=None, extradirs=[], unsafe=False, error_to_output=True, filenumberlimit=128):
    """ Wrapper to execute Commands with the praktomat testuser. Expects Command as list of arguments, the first being the executable to run. """
    assert isinstance(args, list)

    command = args[:]

    environment = os.environ
    environment.update(environment_variables)
    if fileseeklimit is not None:
        fileseeklimitbytes = fileseeklimit * 1024

    sudo_prefix = ["sudo", "-E", "-u", "tester"]

    # Limit the size of files created during execution.
    # In newer versions, R requires more to be started
    # (see comment in RscriptChecker.py),
    # even if it does not use it.
    prlimit_prefix = ['prlimit', '--nofile=%d' % filenumberlimit]
    if fileseeklimit is not None:
        prlimit_prefix += ['--fsize=%d' % fileseeklimitbytes]

    command = prlimit_prefix

    if unsafe:
        pass
    elif settings.USEPRAKTOMATTESTER:
        #command = sudo_prefix
        #fixed: 22.11.2016, Robert Hartmann , H-BRS
        command += deepcopy(sudo_prefix)
    elif settings.USESAFEDOCKER:
        docker_ulimits = [f"nofile={filenumberlimit}"]
        if fileseeklimit is not None:
            docker_ulimits += [f"fsize={fileseeklimitbytes}"]

        safe_docker_cmd, container_name, volumes = safe_docker(
            environment_variables=environment_variables,
            extra_dirs=extradirs,
            maxmem=maxmem,
            ulimits=docker_ulimits,
            working_directory=abspath(working_directory),
        )
        command += safe_docker_cmd

    command += args[:]

    # TODO: Dont even read in output longer than fileseeklimit. This might be most conveniently done by supplying a file like object instead of PIPE

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
		# http://bencane.com/2014/04/01/understanding-the-kill-command-and-how-to-terminate-processes-in-linux/
        term_cmd = ["pkill", "-TERM", "-s", str(process.pid)]
        int_cmd  = ["pkill","-INT","-s",str(process.pid)]
        hup_cmd  = ["pkill","-HUP","-s",str(process.pid)]
        kill_cmd = ["pkill", "-KILL", "-s", str(process.pid)]
        if not unsafe and settings.USEPRAKTOMATTESTER:
            term_cmd = sudo_prefix + term_cmd
            int_cmd = sudo_prefix + int_cmd
            hup_cmd = sudo_prefix + hup_cmd
            kill_cmd = sudo_prefix + kill_cmd
        if not unsafe and settings.USESAFEDOCKER:
            docker_kill_cmd = ["sudo", "docker", "kill", container_name]
            subprocess.call(docker_kill_cmd)
        if unsafe or not settings.USESAFEDOCKER or process.poll() is None:
            # For Docker: in case the "docker kill didn't help"
            subprocess.call(term_cmd)
            time.sleep(5)
            subprocess.call(int_cmd)
            time.sleep(9)
            subprocess.call(hup_cmd)
            time.sleep(5)
            subprocess.call(kill_cmd)
            time.sleep(5)
            if process.poll() is None:
                #if we are here, than we retry to kill the subprocesses in an other way
                kill_proc_tree(pid=process.pid)
                time.sleep(5)
                process.kill()
        [output, error] = process.communicate()
        #killpg(process.pid, signal.SIGKILL)

    # These exit codes originate from the original safe-docker script
    if not unsafe and settings.USESAFEDOCKER and not timed_out and (process.returncode == 255 or process.returncode == 137):
        oom_ed = True

    if not unsafe and settings.USESAFEDOCKER:
        safe_docker_cleanup(volumes)

    return [output.decode('utf-8'), error, process.returncode, timed_out, oom_ed]


def safe_docker(environment_variables, extra_dirs, maxmem, ulimits, working_directory):
    cmd = ["sudo", "docker", "run", "--rm", "--sig-proxy",
        "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", "/home"]

    uid = os.getuid()
    gid = os.getgid()

    if ":" in working_directory:
        raise Exception("working directory contains a ':'")
    for d in extra_dirs:
        if ":" in d:
            raise Exception(f"extra directory 'f{d}' contains a ':'")

    volumes = []
    def add_dir(path, read_only, volumes):
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
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["sudo", "docker", "run", "-d", f"--volume={volume_name}:{path}", "--name",
                helper_name, "busybox", "sleep", "infinity"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["sudo", "docker", "cp", f"{path}.", f"{helper_name}:{path}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["sudo", "docker", "exec", helper_name, "chown", "-R", f"{uid}:{gid}", path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["sudo", "docker", "kill", helper_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        volumes += [{"container": helper_name, "dir": path, "volume": volume_name}]
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
        requires_task_id_custom = var_id in tmpl.get_identifiers()
        if requires_task_id_custom:
            task_id_custom = environment_variables.get(var_id)
            if task_id_custom is not None and task_id_custom != "":
                external_dir = string.Template(settings.DOCKER_CONTAINER_EXTERNAL_DIR).substitute(TASK_ID_CUSTOM=task_id_custom)
        else:
            external_dir = settings.DOCKER_CONTAINER_EXTERNAL_DIR
        if external_dir is not None:
            cmd += [f"--volume={external_dir}:/external:ro"]
    
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


def safe_docker_cleanup(volumes):
    for volume in volumes:
        helper_name = volume["container"]
        volume_name = volume["volume"]
        path = volume["dir"]
        if not settings.DOCKER_DISCARD_ARTEFACTS:
            subprocess.run(
                ["sudo", "docker", "cp", f"{helper_name}:{path}.", path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        subprocess.run(
            ["sudo", "docker", "container", "rm", helper_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["sudo", "docker", "volume", "rm", volume_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
