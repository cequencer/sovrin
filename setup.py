import sys
import os
from setuptools import setup, find_packages, __version__
from pip.req import parse_requirements

v = sys.version_info
if sys.version_info < (3, 5):
    msg = "FAIL: Requires Python 3.5 or later, " \
          "but setup.py was run using {}.{}.{}"
    v = sys.version_info
    print(msg.format(v.major, v.minor, v.micro))
    print("NOTE: Installation failed. Run setup.py using python3")
    sys.exit(1)

# Change to ioflo's source directory prior to running any command
try:
    SETUP_DIRNAME = os.path.dirname(__file__)
except NameError:
    # We're probably being frozen, and __file__ triggered this NameError
    # Work around this
    SETUP_DIRNAME = os.path.dirname(sys.argv[0])

if SETUP_DIRNAME != '':
    os.chdir(SETUP_DIRNAME)

SETUP_DIRNAME = os.path.abspath(SETUP_DIRNAME)

METADATA = os.path.join(SETUP_DIRNAME, 'sovrin', '__metadata__.py')
# Load the metadata using exec() so we don't trigger an import of ioflo.__init__
exec(compile(open(METADATA).read(), METADATA, 'exec'))

reqs = ['git+ssh://git@github.com/evernym/plenum-priv.git@master#egg=plenum',
        'git+https://github.com/jettify/aiohttp_sse.git@master#egg=aiohttp_sse']

for url in reqs:
    os.system('pip install {}'.format(url))

setup(
    name='sovrin',
    version=__version__,
    description='Sovrin Identity',
    long_description='Sovrin Identity',
    author=__author__,
    author_email='dev@evernym.us',
    license=__license__,
    keywords='Sovrin identity plenum',
    packages=find_packages(exclude=['test', 'test.*', 'docs', 'docs*']),
    package_data={
        '':       ['*.txt',  '*.md', '*.rst', '*.json', '*.conf', '*.html',
                   '*.css', '*.ico', '*.png', 'LICENSE', 'LEGAL']},
    install_requires=['base58', 'plyvel'],
    setup_requires=['pytest-runner'],
    tests_require=['pytest']
)