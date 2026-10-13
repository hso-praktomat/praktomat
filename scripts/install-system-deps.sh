#!/usr/bin/env bash
# Installs the system packages needed to build the Python dependencies and to run the test suite.
# Debian/Ubuntu only. Used by CI (.github/workflows/test.yml); run it once in a fresh dev container, too.
#
#   scripts/install-system-deps.sh                      packages for Praktomat and the maintained tests
#   scripts/install-system-deps.sh --checker-toolchains also the compilers/test frameworks for the tests
#                                                       of the R, DejaGnu, C and CUnit/CppUnit checkers
#
# The toolchain tests are marked @requires(..., optional=True): without the toolchains they are skipped,
# even with PRAKTOMAT_REQUIRE_ALL_TOOLS=1. See CLAUDE.md, "Environment-dependent tests".

set -euo pipefail

TOOLCHAINS=0
for arg in "$@"; do
    case "$arg" in
        --checker-toolchains) TOOLCHAINS=1 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

PACKAGES=(
    # build dependencies of python-ldap, psycopg2 and mod_wsgi (requirements.txt)
    gcc libsasl2-dev libldap2-dev libssl-dev libpq-dev apache2-dev
    # used by utilities/safeexec.py (prlimit) and the ScriptChecker tests (bash, perl, seq, pkill)
    util-linux bash perl coreutils procps
    # settings/test.py calls setlocale(en_US.UTF-8) at import time
    locales
)

if [ $TOOLCHAINS -eq 1 ]; then
    PACKAGES+=(dejagnu r-base-core g++ libcunit1-dev libcppunit-dev)
    # The java/javac wrappers in src/checker/scripts use a SecurityManager policy, which needs an old JDK.
    # An existing JDK is kept, unless JDK_PACKAGE is set explicitly.
    if [ -z "${JDK_PACKAGE+set}" ]; then
        JDK_PACKAGE="openjdk-8-jdk"
        if command -v javac >/dev/null; then JDK_PACKAGE=""; fi
    fi
    if [ -n "$JDK_PACKAGE" ]; then PACKAGES+=("$JDK_PACKAGE"); fi
fi

export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends "${PACKAGES[@]}"

if ! locale -a 2>/dev/null | grep -qiE '^en_US\.utf-?8$'; then
    $SUDO sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen || true
    $SUDO locale-gen en_US.UTF-8
fi
