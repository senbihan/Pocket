from setuptools import setup
import sys

if sys.version_info < (2,7) or sys.version_info >= (3,0):
    sys.exit('Sorry, Python < 2.7 and Python >= 3.0 is not supported')

setup(name="Pocket FileSync Server",
	version="0.0.1",
	description="A file server that keeps your file synced.",
	author="Bihan Sen, Shayak Chakraborty",
	author_email="senbihan@gmail.com, shayak.asansol@gmail.com",
	install_requires=[
		'inotify','python-librsync']
)