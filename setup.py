#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import codecs
import platform
from glob import glob
import warnings
import exceptions

from setuptools import setup
from setuptools import Extension
from setuptools.command.build_ext import build_ext


"""
this parameter is used to opt out numpy support in _jpype library
"""
if "--disable-numpy" in sys.argv:
    disabled_numpy = True
    sys.argv.remove("--disable-numpy")
else:
    disabled_numpy = False

class FeatureNotice(exceptions.Warning):
    """ indicate notices about features """
    pass


def read_utf8(*parts):
    filename = os.path.join(os.path.dirname(__file__), *parts)
    return codecs.open(filename, encoding='utf-8').read()

def find_sources():
    cpp_files = []
    for dirpath, dirnames, filenames in os.walk('native'):
        for filename in filenames:
            if filename.endswith('.cpp') or filename.endswith('.c'):
                cpp_files.append(os.path.join(dirpath, filename))
    return cpp_files

def show_error(msg):
    print('*' * 80)
    print(msg)
    print('*' * 80)

platform_specific = {
    'include_dirs': [
        os.path.join('native', 'common', 'include'),
        os.path.join('native', 'python', 'include'),
    ],
    'sources': find_sources(),
}

java_home = os.getenv('JAVA_HOME')
if sys.platform == 'win32':
    if not java_home:
        raise SystemExit('Environment variable JAVA_HOME must be set.')
    platform_specific['libraries'] = ['Advapi32']
    platform_specific['define_macros'] = [('WIN32', 1)]
    platform_specific['include_dirs'] += [
        os.path.join(java_home, 'include'),
        os.path.join(java_home, 'include', 'win32')
    ]
elif sys.platform == 'darwin':
    def getJDKIncludes(java_home):
        possible_includedirs = [os.path.join(java_home, 'Headers'),
                                os.path.join(java_home, 'include'),
                                os.path.join(java_home, 'include/darwin'),
                                # fallback
                                '/System/Library/Frameworks/JavaVM.framework/Headers']
        # make sure jni.h is found - or equivalently this java home is a JDK
        if filter(os.path.exists, [os.path.join(d, 'jni.h') for d in possible_includedirs]) == []:
            show_error('Your current java home does not point to a Java Development Kit (JDK)!\n'
                       'We were not able to find a jni.h file.\n'
                       'Tried with JAVA_HOME=%s\n' 
                       'You can either install the Java Developer package from Apple\n'
                       'OR the OpenJDK from http://oracle.com' % java_home)
            raise RuntimeError
        # return existing include dirs
        return filter(os.path.exists, possible_includedirs)

    if not java_home: # try to estimate, should work solid for osx > 10.5
        osx = platform.mac_ver()[0][:4]
        from distutils.version import StrictVersion

        # for osx > 10.5 we have the nice util /usr/libexec/java_home available
        if StrictVersion(osx) >= StrictVersion('10.6'):
            import subprocess
            # call java_home detector 
            if 'check_output' in dir(subprocess): 
            	java_home = subprocess.check_output(['/usr/libexec/java_home']).strip()
            else:
                java_home = subprocess.Popen(['/usr/libexec/java_home'], stdout=subprocess.PIPE).communicate()[0]
    else: # osx < 10.6
        java_home = '/System/Library/Frameworks/JavaVM.framework/Home/'

    platform_specific['libraries'] = ['dl']
    # this raises warning:
    # distutils/extension.py:133: UserWarning: Unknown Extension options: 'library_dir'
    #platform_specific['library_dir'] = [os.path.join(java_home, 'Libraries')]
    platform_specific['define_macros'] = [('MACOSX', 1)]
    platform_specific['include_dirs'] += getJDKIncludes(java_home)
else:
    if not java_home:
        print "No JAVA_HOME Environment Variable set. Trying to guess it..."
        # (Almost) standard in GNU/Linux
        possible_homes = glob('/usr/lib/jvm/*')
        # Sun/Oracle Java in some cases
        possible_homes += glob('/usr/java/*')
        for home in possible_homes:
            include_path = os.path.join(home, 'include')
            if os.path.exists(include_path):
                java_home = home
                break
        else:
            show_error(
                "No Java/JDK could be found. I looked in the following "
                "directories: \n\n%s\n\nPlease check that you have it "
                "installed.\n\nIf you have and the destination is not in the "
                "above list, please find out where your java's home is, "
                "set your JAVA_HOME environment variable to that path and "
                "retry the installation.\n"
                "If this still fails please open a ticket or create a "
                "pull request with a fix on github: "
                "https://github.com/originell/jpype/"
                % '\n'.join(possible_homes))
            raise RuntimeError
    platform_specific['libraries'] = ['dl']
    #platform_specific['library_dir'] = [os.path.join(java_home, 'lib')]
    platform_specific['include_dirs'] += [
        os.path.join(java_home, 'include'),
        os.path.join(java_home, 'include', 'linux'),
    ]


jpypeLib = Extension(name='_jpype', **platform_specific)
       
class my_build_ext(build_ext):
    """
    Override some behavior in extension building:
    
    1. Numpy:
        If not opted out, try to use NumPy and define macro 'HAVE_NUMPY', so arrays
        returned from Java can be wrapped efficiently in a ndarray.
    2. handle compiler flags for different compilers via a dictionary.
    3. try to disable warning ‘-Wstrict-prototypes’ is valid for C/ObjC but not for C++
    """
    
    # extra compile args
    copt = {'msvc': ['/EHsc'],
            'gcc' : [],
            'mingw32' : [],
           }
    # extra link args
    lopt = {
            'mingw32' : [],
           }
    
    def initialize_options(self, *args):
        """omit -Wstrict-prototypes from CFLAGS since its only valid for C code."""
        from distutils.sysconfig import get_config_vars
        (opt,) = get_config_vars('OPT')
        if opt:
            os.environ['OPT'] = ' '.join(flag for flag in opt.split() 
                                         if flag != '-Wstrict-prototypes')
            
        build_ext.initialize_options(self)
        
    def build_extensions(self):
        # set compiler flags
        c = self.compiler.compiler_type
        if self.copt.has_key(c):
           for e in self.extensions:
               e.extra_compile_args = self.copt[ c ]
        if self.lopt.has_key(c):
            for e in self.extensions:
                e.extra_link_args = self.lopt[ c ]

        # handle numpy
        if not disabled_numpy:
            try:
                import numpy
                jpypeLib.define_macros.append(('HAVE_NUMPY', 1))
                jpypeLib.include_dirs.append(numpy.get_include())
                warnings.warn("Turned ON Numpy support for fast Java array access",
                               FeatureNotice)
            except ImportError:
                pass
        else:
            warnings.warn("Turned OFF Numpy support for fast Java array access",
                          FeatureNotice)
        
        # has to be last call
        build_ext.build_extensions(self)

setup(
    name='JPype1',
    version='0.5.5.4',
    description='A Python to Java bridge.',
    long_description=(read_utf8('README.rst') + '\n\n' +
                      read_utf8('doc/CHANGELOG.rst') + '\n\n' +
                      read_utf8('AUTHORS.rst')),
    license='License :: OSI Approved :: Apache Software License',
    author='Steve Menard',
    author_email='devilwolf@users.sourceforge.net',
    maintainer='Luis Nell',
    maintainer_email='cooperate@originell.org',
    url='https://github.com/originell/jpype/',
    platforms=[
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows :: Windows 7',
        'Operating System :: Microsoft :: Windows :: Windows Vista',
        'Operating System :: POSIX :: Linux',
    ],
    classifiers=[
        'Programming Language :: Java',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ],
    packages=[
        'jpype', 'jpype.awt', 'jpype.awt.event', 'jpypex', 'jpypex.swing'],
    package_dir={
        'jpype': 'jpype',
        'jpypex': 'jpypex',
    },
    extras_require = {'numpy' : ['numpy>=1.6']},
    cmdclass={'build_ext': my_build_ext},
    #zip_safe=False,
    ext_modules=[jpypeLib],
)
