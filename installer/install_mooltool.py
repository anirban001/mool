#!/usr/bin/env python2.7
"""Script to install mooltool on developer and test machines. We use python
virtual environment based approach for setting up the development environment.

Required packages before the script can be used are:
* Java >= 1.7.0
* python >= 2.7.3
* G++

It is supposed to work on Mac OS, Ubuntu and Centos.
Please visit mool wiki https://github.com/rocketfuel/mool/wiki for help on
installation of prerequisites.
"""

import errno
import hashlib
import logging
import os
import shlex
import shutil
import subprocess
import sys
import urllib

MIN_PYTHON_VERSION = (2, 7, 3)
INSTALL_HELP_MSG = (
    '**** Refer to {0} link for installation instructions ****'.format(
        'https://github.com/rocketfuel/mool/wiki'))

# Fail if not running required python version.
if MIN_PYTHON_VERSION <= sys.version_info[0:3]:
    import argparse
else:
    print 'Current python version is %s' % sys.version[0:5]
    print 'Please install python version >= 2.7.3'
    print INSTALL_HELP_MSG
    sys.exit(1)


def parse_command_line():
    """Parses command line to generate arguments."""
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        '-d', '--install_dir', type=str, default='',
        help='Installation path for mool. Default user HOME.')
    arg_parser.add_argument(
        '-j', '--java_home', type=str, default=os.environ.get('JAVA_HOME'),
        help='Path to JAVA Home. Default JAVA_HOME environment variable.')
    arg_parser.add_argument(
        '-t', '--test_only', default=False,
        action='store_true', help='Test current mool installation.')
    arg_parser.add_argument(
        '-fi', '--fresh', default=False, action='store_true',
        help='Erase existing and install fresh copy of mool.')
    return arg_parser


# Due to very tight dependency on INSTALL_DIR, we need to set it here.
# Keep the default value unless you are very eager to change/test it.
THIS_SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
INSTALL_DIR = (os.path.abspath(parse_command_line().parse_args().install_dir)
               or os.path.dirname(THIS_SCRIPT_DIR))

MOOL_INSTALL_DIR = os.path.join(INSTALL_DIR, '.rfmool')
MOOL_INIT_SCRIPT = os.path.join(MOOL_INSTALL_DIR, 'mool_init.sh')
MOOL_PACKAGES_DIR = os.path.join(MOOL_INSTALL_DIR, 'packages')
MOOL_RC_FILE = os.path.join(MOOL_INSTALL_DIR, 'moolrc')
MOOL_CUSTOM_RC_FILE = os.path.join(MOOL_INSTALL_DIR, 'moolrc_custom')
BUILD_TOOLS_DIR = os.path.join(MOOL_INSTALL_DIR, 'ei.build_tools')
BU_SCRIPT_DIR = os.path.join(BUILD_TOOLS_DIR, 'bu.scripts')
CC_INSTALL_PREFIX = os.path.join(MOOL_PACKAGES_DIR, 'cc_libs')
CC_INSTALL_LIBS = os.path.join(CC_INSTALL_PREFIX, 'lib')
CC_INSTALL_HEADERS = os.path.join(CC_INSTALL_PREFIX, 'include')
TEMP_DIR = os.path.join(MOOL_INSTALL_DIR, '.temp')
JAR_SEARCH_PATH = os.path.join(MOOL_INSTALL_DIR, 'jars')
VIRTUALENV_PATH = os.path.join(MOOL_INSTALL_DIR, 'MOOL_ENV')
OPENSSL_INSTALL_PATH = os.environ.get('OPENSSL_INSTALL_PATH', None)

BOOST_PACKAGE = (('http://downloads.sourceforge.net/project/boost/boost/'
                  '1.58.0/boost_1_58_0.tar.bz2'), 'boost_1_58_0',
                 '2fc96c1651ac6fe9859b678b165bd78dc211e881')
THRIFT_PACKAGE = (('http://www.us.apache.org/dist/thrift/0.9.1/'
                   'thrift-0.9.1.tar.gz'), 'thrift-0.9.1',
                  'dc54a54f8dc706ffddcd3e8c6cd5301c931af1cc')
# Above source code compiles fine of linux machines (given you have all deps
# satisfied) but for MAC, it doesn't compile as clang compiler doesn't expose
# std::tr1 headers. So we patch it to use tr1 headers from boost-1.58.0.
THRIFT_PATCH = ((
    'https://gist.githubusercontent.com/kumarjatin/4b8fc3389696b96b23d9/raw/'
    'caadb7040b6f05e72625dcb82f581b526b5890f7/withoutcxx11.patch'),
    '2f5b99e03977ac480ec7207b7cebb9f82d32bde3')

VIRTUALENV_URL = (('https://pypi.python.org/packages/source/v/virtualenv/'
                   'virtualenv-1.11.6.tar.gz'), 'virtualenv-1.11.6',
                  'd3f8e94bf825cc999924e276c8f1c63b8eeb0715')

JAVA_PROTOBUF_JAR = 'protobuf-2.5.0.jar'
PROTOBUF_PACKAGE = (('https://protobuf.googlecode.com/files/'
                     'protobuf-2.5.0.tar.bz2'), 'protobuf-2.5.0',
                    '62c10dcdac4b69cc8c6bb19f73db40c264cb2726')

PIP_INSTALL_PACKAGES = [('pylint', '0.28.0'), ('pep8', '1.4.5'),
                        ('pytest', '2.3.4')]

SCALA_2_11 = ('http://www.scala-lang.org/files/archive/scala-2.11.4.tgz',
              'scala-2.11.4', 'a6d319b26ccabe9c609fadebc32e797bf9cb1084')
SCALA_2_10 = ('http://www.scala-lang.org/files/archive/scala-2.10.4.tgz',
              'scala-2.10.4', '970f779f155719838e81a267a7418a958fd4c13f')
SCALA_2_8 = ('http://www.scala-lang.org/files/archive/scala-2.8.2.final.tgz',
             'scala-2.8.2.final', '2d6250763dcba02f371e0c26999a4f43670e8e3e')

GMOCK_PACKAGE = ('https://googlemock.googlecode.com/files/gmock-1.7.0.zip',
                 'f9d9dd882a25f4069ed9ee48e70aff1b53e3c5a5', 'gmock-1.7.0')
GMOCK_BUILD_COMMANDS = [
    ('gcc -isystem ${GTEST_DIR}/include -I${GTEST_DIR}'
     ' -isystem ${GMOCK_DIR}/include -I${GMOCK_DIR}'
     ' -o${TARGET_DIR}/gtest-all.o -pthread -c ${GTEST_DIR}/src/gtest-all.cc'),
    ('gcc -isystem ${GTEST_DIR}/include -I${GTEST_DIR}'
     ' -isystem ${GMOCK_DIR}/include -I${GMOCK_DIR}'
     ' -o${TARGET_DIR}/gmock-all.o -pthread -c ${GMOCK_DIR}/src/gmock-all.cc'),
    ('gcc -isystem ${GTEST_DIR}/include -I${GTEST_DIR}'
     ' -c ${GTEST_DIR}/src/gtest_main.cc -o ${TARGET_DIR}/gtest_main.o'),
    ('ar -rv ${TARGET_DIR}/libgmock.a ${TARGET_DIR}/gtest-all.o'
     ' ${TARGET_DIR}/gmock-all.o')]
MOOL_AUTOCOMPLETE_SCRIPT = 'mool_autocomplete.sh'
MOOL_INIT_TEMPLATE_FILE = 'mool_init_template.sh'
MOOL_INIT_VARS = (
    'BOOST_DIR', 'BUILD_TOOLS_ROOT', 'CC_INSTALL_PREFIX', 'GTEST_MAIN_LIB',
    'GTEST_MOCK_LIB', 'JAR_SEARCH_PATH', 'JAVA_HOME', 'JAVA_PROTOBUF_JAR',
    'PROTO_COMPILER', 'PYTHON_PROTOBUF_DIR', 'SCALA_DEFAULT_VERSION',
    'SCALA_HOME_2_10', 'SCALA_HOME_2_11', 'SCALA_HOME_2_8', 'THRIFT_DIR')
VARS_TO_EXPORT = {}
VARS_TO_EXPORT['BUILD_TOOLS_ROOT'] = BUILD_TOOLS_DIR
VARS_TO_EXPORT['CC_INSTALL_PREFIX'] = CC_INSTALL_PREFIX
VARS_TO_EXPORT['JAR_SEARCH_PATH'] = JAR_SEARCH_PATH
VARS_TO_EXPORT['SCALA_DEFAULT_VERSION'] = '2.8'

BLOCK_SIZE = 1 << 20
LOGGER = None
LOG_FILE_PATH = os.path.join(TEMP_DIR, 'mool_install.log')
PROGRESS_BAR = '\rDownload: [{}{}] {:>3}%'

MOOLRC_TEXT = """
export MOOL_INIT_SCRIPT="VAR_MOOL_INIT_SCRIPT"
export MOOL_VIRTUALENV="VAR_VIRTUALENV_PATH"

function mool_init() {
  source "${MOOL_VIRTUALENV}"
  source "${MOOL_INIT_SCRIPT}"
  alias bu="${BU_SCRIPT_DIR}/bu"
  source "VAR_MOOL_AUTOCOMPLETE"
}
"""
INSTALL_SUCCESS_MSG = """
********** Successfully installed build tool mool in {0} directory! **********
* Mool has been configure to use python virtual environment that points to {1}.
* Mool environment settings are in {2} file which you may want to look at.
* Entry for mool_init function has been added to {3}/moolrc file.
  You may want to add "source {3}/moolrc" in your bashrc/zshrc file.
* Execute `source {3}/moolrc && mool_init` to activate mool environment.
"""


class Error(Exception):
    """Error class for this script."""
    def __exit__(self, etype, value, traceback):
        LOGGER.error(self.message)


def check_sha_sum(file_path, sha_sum):
    """Check sha sum of a given file."""
    hash_object = hashlib.sha1()
    with open(file_path, 'r') as file_object:
        while True:
            file_text = file_object.read(BLOCK_SIZE)
            if not file_text:
                break
            hash_object.update(file_text)
    if hash_object.hexdigest() != sha_sum:
        raise Error('Sha1 mismatch for file {}!!'.format(file_path))


def download_item(url, file_path, sha_sum):
    """Download url to file path. This function intially checks if the file
    exists and re-downloads only if necessary."""
    def report_hook(count, block_size, total_size):
        """Handler for urllib report hook."""
        done = (block_size * count * 50 / total_size)
        print PROGRESS_BAR.format('=' * done, ' ' * (50 - done), done * 2),
        sys.stdout.flush()
    # check for pre existence
    if os.path.exists(file_path):
        try:
            check_sha_sum(file_path, sha_sum)
            return
        except Error:
            _execute(['rm', '-f', file_path])
    # downloading the item
    temp_path = file_path + '.temp'
    LOGGER.info('Downloading %s to %s.', url, file_path)
    urllib.urlretrieve(url, temp_path, reporthook=report_hook)
    check_sha_sum(temp_path, sha_sum)
    shutil.move(temp_path, file_path)


def mkdir_p(path):
    """Create directory along with all required parent directories."""
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno != errno.EEXIST or not os.path.isdir(path):
            raise


def copy_all(src_path, dst_path):
    """Recursively copy everything from src_path to dst_path."""
    flags = '-rf' if os.path.isdir(src_path) else '-f'
    _execute(['cp', flags, src_path, dst_path])


def configure_logging(console=True):
    """Setup logging. Enable console logging by default."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    if console:
        console_handle = logging.StreamHandler(sys.stdout)
        console_handle.setLevel(logging.INFO)
        console_handle.setFormatter(
            logging.Formatter('%(levelname)s: %(message)s'))
        logger.addHandler(console_handle)
    return logger


def _execute(command, stdout=False, use_shell=False):
    """Executes a given command and logs stdout to file."""
    LOGGER.info('Executing "%s".', ' '.join(command))
    try:
        if not stdout:
            with open(LOG_FILE_PATH, 'a') as log_obj:
                subprocess.check_call(command, stdout=log_obj, shell=use_shell)
        else:
            subprocess.check_call(command, shell=use_shell)
    except subprocess.CalledProcessError:
        LOGGER.error('Command %s failed!!', ' '.join(command))
        raise


def _check_dependencies():
    """Check for preinstalled dependencies required for mool."""
    LOGGER.info('Checking support for JAVA.')
    try:
        javac_bin = os.path.join(VARS_TO_EXPORT['JAVA_HOME'], 'bin', 'javac')
        output = subprocess.check_output([javac_bin, '-version'],
                                         stderr=subprocess.STDOUT).strip()
        version = tuple([int(v) for v in output.split(' ')[1].split('.')[0:2]])
        if version < (1, 7):
            raise Error(('Java version found: %s, min required: %s. '
                         'Aborting installation!'), output, '1.7')
    except OSError:
        LOGGER.error('Java support not found. Aborting installation!!')
        LOGGER.error(INSTALL_HELP_MSG)
        raise
    LOGGER.info('Checking ant, required for thrift java compilation.')
    try:
        _execute(['ant', '-version'])
    except OSError:
        LOGGER.error('ant binary not found!')
        LOGGER.error(INSTALL_HELP_MSG)
        raise
    LOGGER.info('Checking OpenSSL version required > 1.0.0 for thrift libs')
    try:
        openssl = 'openssl'
        if OPENSSL_INSTALL_PATH:
            openssl = os.path.join(OPENSSL_INSTALL_PATH, 'bin', 'openssl')

        output = subprocess.check_output([openssl, 'version'],
                                         stderr=subprocess.STDOUT).strip()
        version = tuple([int(v) for v in output.split(' ')[1].split('.')[0:2]])
        if version < (1, 0):
            LOGGER.error(('OpenSSL version found: %s, min required: %s. '
                          'Aborting installation!'), output, '1.0')
            raise Error(('Use OPENSSL_INSTALL_PATH key to use custom '
                         'OpenSSL installation'))
    except OSError:
        LOGGER.error('openssl binary not found!')
        LOGGER.error(INSTALL_HELP_MSG)
        raise
    LOGGER.info('All dependency checks passed.')


def _check_done_file():
    """Checks if done marker file exists in current working directory."""
    return os.path.exists(DONE_MARKER_FILE)


def _create_done_file():
    """Create done marker file in current working directory."""
    marker = open(DONE_MARKER_FILE, 'w')
    marker.close()


def _setup_virtualenv():
    """Install and activate python virtual environment."""
    try:
        version = subprocess.check_output(['virtualenv', '--version'])
        LOGGER.info('Using existing virtualenv version: %s', version)
        _execute(['virtualenv', '-p', sys.executable, VIRTUALENV_PATH])
    except OSError:
        os.chdir(MOOL_PACKAGES_DIR)
        url, dir_name, sha_sum = VIRTUALENV_URL
        dest_path = os.path.join(os.path.abspath('.'), os.path.basename(url))
        download_item(url, dest_path, sha_sum)
        _execute(['tar', '-zxf', dest_path])
        script = os.path.join('.', dir_name, 'virtualenv.py')
        _execute(['python', script, '-p', sys.executable, VIRTUALENV_PATH])
    activate_this = os.path.join(VIRTUALENV_PATH, 'bin', 'activate_this.py')
    execfile(activate_this, dict(__file__=activate_this))


def _pip_install_packages(packages):
    """Install packages using pip."""
    for package, version in packages:
        full_name = '{}=={}'.format(package, version)
        LOGGER.info('Installing %s.', full_name)
        _execute(['pip', 'install', full_name])


def _install_scala():
    """Untars the scala installation packages and exports env. variables."""
    os.chdir(MOOL_PACKAGES_DIR)
    for package, env_var in [(SCALA_2_8, 'SCALA_HOME_2_8'),
                             (SCALA_2_10, 'SCALA_HOME_2_10'),
                             (SCALA_2_11, 'SCALA_HOME_2_11')]:
        url, dir_name, sha_sum = package
        LOGGER.info('Setting up %s', dir_name)
        dest_path = os.path.join(os.path.abspath('.'), os.path.basename(url))
        download_item(url, dest_path, sha_sum)
        _execute(['tar', '-zxf', dest_path])
        VARS_TO_EXPORT[env_var] = os.path.join(os.path.abspath('.'), dir_name)


def _download_protobuf():
    """Download protobuf source."""
    os.chdir(MOOL_PACKAGES_DIR)
    url, dir_name, sha_sum = PROTOBUF_PACKAGE
    dest_path = os.path.join(os.path.abspath('.'), os.path.basename(url))
    download_item(url, dest_path, sha_sum)
    _execute(['tar', '-xf', dest_path])
    return os.path.join(MOOL_PACKAGES_DIR, dir_name)


def _setup_protobuf():
    """Download and install protobuf."""
    LOGGER.info('Setting up Protobuf-2.5.0')
    os.chdir(_download_protobuf())
    cur_dir = os.path.abspath('.')

    # Add missing '<iostream>' library in src/google/protobuf/message.cc file.
    bad_file = 'src/google/protobuf/message.cc'
    with open(os.path.join(cur_dir, bad_file), 'r+') as file_obj:
        msg_file_contents = file_obj.readlines()
        msg_file_contents.insert(35, '#include <iostream>\n')
        file_obj.seek(0)
        file_obj.write(''.join(msg_file_contents))

    # Build and install protobuf in local directory.
    _execute(['./configure', '--prefix={}'.format(cur_dir),
              '--disable-shared', '--enable-static'])

    _execute(['make', 'install'])
    protoc_binary = os.path.join(cur_dir, 'bin', 'protoc')
    assert os.path.exists(protoc_binary)
    VARS_TO_EXPORT['PROTO_COMPILER'] = protoc_binary

    os.chdir(os.path.join(cur_dir, 'python'))
    _execute(['python', 'setup.py', 'build'])
    lib_dir = os.listdir('build')[0]
    VARS_TO_EXPORT['PYTHON_PROTOBUF_DIR'] = os.path.join(os.path.abspath('.'),
                                                         'build', lib_dir)

    os.chdir(os.path.join(cur_dir, 'java'))
    _execute([protoc_binary, '--java_out=src/main/java', '-I../src',
              '../src/google/protobuf/descriptor.proto'])
    target_dir = os.path.join(os.path.abspath('.'), 'target')
    mkdir_p(target_dir)
    javac_bin = os.path.join(VARS_TO_EXPORT['JAVA_HOME'], 'bin', 'javac')
    command = [javac_bin, '-d', target_dir]
    src_dir = os.path.join(os.path.abspath('.'),
                           'src/main/java/com/google/protobuf/')
    command.extend([os.path.join(src_dir, f) for f in os.listdir(src_dir)])
    _execute(command)
    os.chdir(target_dir)
    jar_bin = os.path.join(VARS_TO_EXPORT['JAVA_HOME'], 'bin', 'jar')
    _execute([jar_bin, '-cf', JAVA_PROTOBUF_JAR, 'com'])
    protobuf_jar_path = os.path.join(target_dir, JAVA_PROTOBUF_JAR)
    assert os.path.exists(protobuf_jar_path)
    VARS_TO_EXPORT['JAVA_PROTOBUF_JAR'] = protobuf_jar_path


def _install_cc_packages():
    """Install commonly used cc build tools."""
    # TODO: Use done marker to avoid repetition during update.
    for directory in [CC_INSTALL_PREFIX, CC_INSTALL_LIBS, CC_INSTALL_HEADERS]:
        mkdir_p(directory)
    os.chdir(MOOL_PACKAGES_DIR)

    # Install support Google Mock.
    url, sha_sum, base_name = GMOCK_PACKAGE
    download_path = os.path.join(MOOL_PACKAGES_DIR, os.path.basename(url))
    download_item(url, download_path, sha_sum)
    _execute(['unzip', '-uq', download_path], stdout=True)
    gmock_dir = os.path.join(MOOL_PACKAGES_DIR, base_name)
    for cmd in GMOCK_BUILD_COMMANDS:
        cmd = cmd.replace('${GTEST_DIR}', os.path.join(gmock_dir, 'gtest'))
        cmd = cmd.replace('${GMOCK_DIR}', os.path.join(gmock_dir))
        cmd = cmd.replace('${TARGET_DIR}', CC_INSTALL_LIBS)
        _execute(shlex.split(cmd.replace('\n', ' ')), stdout=True)
    copy_all(os.path.join(gmock_dir, 'include', 'gmock'), CC_INSTALL_HEADERS)
    copy_all(os.path.join(gmock_dir, 'gtest', 'include', 'gtest'),
             CC_INSTALL_HEADERS)
    VARS_TO_EXPORT['GTEST_MAIN_LIB'] = os.path.join(CC_INSTALL_LIBS,
                                                    'gtest_main.o')
    VARS_TO_EXPORT['GTEST_MOCK_LIB'] = os.path.join(CC_INSTALL_LIBS,
                                                    'libgmock.a')

    # Install protobuf static libs and headers.
    proto_dir = os.path.join(MOOL_PACKAGES_DIR, 'protobuf-2.5.0')
    for lib in os.listdir(os.path.join(proto_dir, 'lib')):
        if lib.find('.so') < 0:
            copy_all(os.path.join(proto_dir, 'lib', lib), CC_INSTALL_LIBS)
    copy_all(os.path.join(proto_dir, 'include', 'google'), CC_INSTALL_HEADERS)


def _install_boost():
    """Download, compile, package and install boost 1.58.0 libraries."""
    os.chdir(MOOL_PACKAGES_DIR)
    url, dir_name, sha_sum = BOOST_PACKAGE
    dest_path = os.path.join(os.path.abspath('.'), os.path.basename(url))
    download_item(url, dest_path, sha_sum)
    _execute(['tar', '-xf', dest_path])
    os.chdir(dir_name)
    _execute(['./bootstrap.sh'], stdout=True)
    target_dir = os.path.join(os.path.abspath('.'), 'target')
    mkdir_p(target_dir)
    _execute(['./b2', '--prefix=' + target_dir, 'link=static', 'install'],
             stdout=True)
    VARS_TO_EXPORT['BOOST_DIR'] = target_dir


def _install_thrift():
    """Download, compile, package and install thrift 0.9.1 libraries."""
    os.chdir(MOOL_PACKAGES_DIR)
    url, dir_name, sha_sum = THRIFT_PACKAGE
    dest_path = os.path.join(os.path.abspath('.'), os.path.basename(url))
    download_item(url, dest_path, sha_sum)
    _execute(['tar', '-xf', dest_path])
    os.chdir(dir_name)
    patch_url, sha_sum = THRIFT_PATCH
    patch = os.path.join(os.path.abspath('.'), os.path.basename(patch_url))
    download_item(patch_url, patch, sha_sum)
    try:
        _execute(['patch', '-p1', '-d', '.', '-N', '-i', patch], stdout=True)
    except subprocess.CalledProcessError:
        LOGGER.info('Assuming thrift patch is already applied!')
    target_dir = os.path.join(os.path.abspath('.'), 'target')
    mkdir_p(target_dir)
    os.environ['PY_PREFIX'] = target_dir
    os.environ['JAVA_PREFIX'] = target_dir
    openssl_opt = ''
    if OPENSSL_INSTALL_PATH:
        openssl_opt = '--with-openssl=' + OPENSSL_INSTALL_PATH
    _execute(['./configure', '--with-lua=no', '--with-perl=no',
              '--with-php=no', '--with-ruby=no', openssl_opt,
              '--with-boost=' + VARS_TO_EXPORT['BOOST_DIR'], '--disable-shared',
              '--prefix=' + target_dir], stdout=True)
    _execute(['make', 'install'], stdout=True)
    mkdir_p(os.path.join(target_dir, 'pylib'))

    # Python libs are copied to platform specific location.
    lib_dir = os.path.join(target_dir, 'lib')
    lib64_dir = os.path.join(target_dir, 'lib64')
    py_dir = None
    for directory in (lib_dir, lib64_dir):
        if not os.path.exists(directory):
            continue
        py_dir = [d for d in os.listdir(directory) if d.startswith('python')]
        if len(py_dir) > 0:
            py_dir = os.path.join(
                directory, py_dir[0], 'site-packages', 'thrift')
            break
    copy_all(py_dir, os.path.join(target_dir, 'pylib'))
    VARS_TO_EXPORT['THRIFT_DIR'] = target_dir


def _setup_mool_init():
    """Creates the mool_init.sh file."""
    LOGGER.info('Creating mool init script.')
    mool_init_template = os.path.join(THIS_SCRIPT_DIR, MOOL_INIT_TEMPLATE_FILE)
    file_contents = None
    with open(mool_init_template, 'r') as template_file:
        file_contents = template_file.read()
    for var in MOOL_INIT_VARS:
        file_contents = file_contents.replace('VAR_{}'.format(var),
                                              VARS_TO_EXPORT[var])
    with open(MOOL_INIT_SCRIPT, 'w') as init_file:
        init_file.write(file_contents)
    text = MOOLRC_TEXT.replace('VAR_MOOL_INIT_SCRIPT', MOOL_INIT_SCRIPT)
    env_activate = os.path.join(VIRTUALENV_PATH, 'bin', 'activate')
    text = text.replace('VAR_VIRTUALENV_PATH', env_activate)
    mool_autocomplete = os.path.join(THIS_SCRIPT_DIR, MOOL_AUTOCOMPLETE_SCRIPT)
    dest_path = os.path.join(MOOL_INSTALL_DIR, MOOL_AUTOCOMPLETE_SCRIPT)
    shutil.copy(mool_autocomplete, dest_path)
    text = text.replace('VAR_MOOL_AUTOCOMPLETE', dest_path)
    with open(MOOL_RC_FILE, 'w') as moolrc_obj:
        moolrc_obj.write(text)
    os.chdir(THIS_SCRIPT_DIR)


def test_setup():
    """Run all the mool tests on the current setup."""
    LOGGER.info('Running mool tests using current environment setup.')
    os.chdir(THIS_SCRIPT_DIR)
    activate_this = os.path.join(VIRTUALENV_PATH, 'bin', 'activate_this.py')
    execfile(activate_this, dict(__file__=activate_this))
    test_script = os.path.join(os.path.dirname(THIS_SCRIPT_DIR), 'test_all.sh')
    _execute(['bash', test_script], stdout=True)


def _erase_existing_install():
    """Delete the existing mool installation."""
    LOGGER.warn('Removing existing mool installation from %s!', INSTALL_DIR)
    for dir_path in [VIRTUALENV_PATH, MOOL_PACKAGES_DIR, BUILD_TOOLS_DIR]:
        if os.path.exists(dir_path):
            _execute(['rm', '-rf', dir_path])


def _install_all():
    """Installer utility for mool tool."""
    LOGGER.info('**** Check %s for installation logs. ****', LOG_FILE_PATH)
    _check_dependencies()
    _setup_virtualenv()
    _pip_install_packages(PIP_INSTALL_PACKAGES)
    _setup_protobuf()
    _install_cc_packages()
    _install_boost()
    _install_thrift()
    _install_scala()
    _setup_mool_init()
    test_setup()
    LOGGER.info(INSTALL_SUCCESS_MSG.format(INSTALL_DIR, VIRTUALENV_PATH,
                                           MOOL_INIT_SCRIPT, MOOL_INSTALL_DIR))


def main():
    """Main function to drive mool tool setup."""
    arg_parser = parse_command_line()
    args = arg_parser.parse_args()
    LOGGER.info('Using "{}" as installation directory.'.format(INSTALL_DIR))
    if not args.java_home or not os.path.exists(args.java_home):
        LOGGER.error('Invalid JAVA_HOME value.')
        arg_parser.print_help()
        sys.exit(1)
    VARS_TO_EXPORT['JAVA_HOME'] = args.java_home.rstrip('/')
    if args.test_only:
        return test_setup()
    if args.fresh:
        _erase_existing_install()
    mkdir_p(MOOL_INSTALL_DIR)
    mkdir_p(TEMP_DIR)
    mkdir_p(MOOL_PACKAGES_DIR)
    _install_all()


if __name__ == '__main__':
    LOGGER = configure_logging()
    try:
        main()
    except Exception:
        LOGGER.exception(sys.exc_info())
        print INSTALL_HELP_MSG
