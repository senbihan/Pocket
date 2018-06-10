# pocket : A simple file synchronisation server-client application 

**Introduction**:

pocket is small dropbox-like client that keeps your files synced. This is a collaborative class project of Operating Subject Indian Statistical Institute, Kolkata for M.Tech CS Batch 2017-19.

****
**Current Features**

1. Upload files from local machine to server that are not present.
2. Synchronise existing files with the server.

**Features to be Added**

1. Single user multi-client support
2. Multiple user support.

**Dependency:**

To Run, Test you need these :

1. librsync :
     >For Debian/Ubuntu<br/>

      1. run `sudo apt-get install librsync-dev`. (for librsync library)      
      2. run `sudo pip install python-librsync`.  (for python wrapper)

2. inotify  :
      >For Debian/Ubuntu
      
      1. run `sudo apt-get inotify-tools`.   (for inotify library)      
      2. run `sudo pip install inotify`  .   (for python wrapper)

Otherwise, you can install librsync and inotify library and then            
run `$sudo python setup.py install` to install the python wrappers.

**Credits**

Credits for the open-source library used in this project:<br/>
https://github.com/dsoprea/PyInotify    (pynotify)<br/>
https://github.com/smartfile/python-librsync    (librsync)