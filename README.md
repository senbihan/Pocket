# pocket : A simple file server-client application 

**Introduction**:

pocket is small dropbox-like client that keeps your files synced. This is a collaborative class project of Operating Subject Indian Statistical Institute, Kolkata for M.Tech CS Batch 2017-19.

****
# Change Log:

**Latest addition**:
1. 29/04/2018:  Initial Commit - Simple client server message - acknowledgement
2. 13/05/2018:  DBops updated.

**Next to be added:**
1. Notifier (`inotify`) to watch over changes in local directories
2. Synchronization with the server
3. Handling multiple clients
4. Synchronization between multiple alive sessions of a single Client


**Dependency:**
1. This project requires `inotify`.

   run `$sudo python setup.py install` from terminal to install the dependencies.