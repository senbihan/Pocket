import sys
import os
import socket
import getpass
import inotify.adapters
import time
import pocketmsg as pm
import logging
import thread
import traceback
from threading import Thread
import threading
import librsync as sync
import tempfile


BUFFER_SIZE     =   1024
MAX_SPOOL       =   1024 ** 2 * 5
SERVER_IP       =   ''
C_DATA_SOCK_PORT = pm.SharedPort.client_port
S_DATA_SOCK_PORT = pm.SharedPort.server_port
tempFiles = []
tempdelFiles = []
tempmvFiles = []
locked = {}
conflict = {}
delreq = {}

USAGE_MESG      = '''Pocket : A simple fileserver synced with your local directories

usage : python client.py [path to the directory] [ip] [port] [client_id]
'''
client_id = ''
logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(message)s')

def wait_net_service(s, server, port, timeout=None):
    """ Wait for network service to appear 
        @param timeout: in seconds, if None or 0 wait forever
        @return: True of False, if timeout is None may return only True or
                 throw unhandled network exception
    """
    import errno

    #s = socket.socket()
    if timeout:
        from time import time as now
        # time module is needed to calc timeout shared between two exceptions
        end = now() + timeout

    while True:
        try:
            if timeout:
                next_timeout = end - now()
                if next_timeout < 0:
                    return False
                else:
            	    s.settimeout(next_timeout)
            
            s.connect((server, port))
        
        except socket.timeout, err:
            # this exception occurs only if timeout is set
            if timeout:
                return False
      
        except socket.error, err:
            # catch timeout exception from underlying network library
            # this one is different from socket.timeout
            if type(err.args) != tuple or err[0] != errno.ETIMEDOUT:
                continue
        else:
            # s.close()
            return True


def send_signature(file_name):
    
    # connect for sync
    client_sig_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    wait_net_service(client_sig_socket, SERVER_IP ,pm.SharedPort.server_sig_port)

    # calculate signature
    sig = sync.signature(open(file_name,"rb+"))

    # logging.info("sending signature of file : %s",file_name)
    
    l = sig.read(BUFFER_SIZE)
    while l:
        client_sig_socket.send(l)
        l = sig.read(BUFFER_SIZE)
    sig.close()
    client_sig_socket.close()
    
    logging.info("Signature Sent!")


def service_message(msg, client_socket, db_conn):

    global tempdelFiles, tempFiles, tempmvFiles, locked, conflict, delreq

    if db_conn is None:
        db_conn = pm.open_db()

    msg_code, client_id, file_name, data = msg.split(pm.msgCode.delim)

    if msg_code == pm.msgCode.REQTOT:
        header = pm.get_senddat_msg(client_id,file_name, db_conn)
        #logging.info("sending : header = %s", header)
        client_socket.send(header)
        
        client_data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #logging.debug("waiting for data socket to be ready..")
        wait_net_service(client_data_socket,SERVER_IP,S_DATA_SOCK_PORT, 10)
        #client_data_socket.connect(server_data_address)
        #logging.debug("Connected")
        with open(file_name, 'rb') as f:
            l = f.read(BUFFER_SIZE)
            while l:
                client_data_socket.send(l)
                l = f.read(BUFFER_SIZE)
            f.close()
        logging.debug("file sent: %s", file_name)
        client_data_socket.close()
        return 1

    if msg_code == pm.msgCode.SENDSMT:
        #logging.info("updating server_m_time of %s to %s",file_name,data)
        pm.update_db(db_conn,file_name,"server_m_time",data)
        db_conn.commit()
        return 0

        
    if msg_code == pm.msgCode.SENDSIG:
        
        #compute delta and send
        
        sig_socket = socket.socket()
        addr = ('', pm.SharedPort.client_sig_port)
        sig_socket.bind(addr)
        #print "Client sig socket is ready at: {}".format(data_socket.getsockname())
        sig_socket.listen(10)
        server_sig_sock, addr = sig_socket.accept()
        
        # Receive Signature
        sigdata = ""
        while True:
            data = server_sig_sock.recv(BUFFER_SIZE)
            sigdata += data
            if not data:
                break
        
        server_sig_sock.close()
        sig_socket.close()
        
        logging.info("Signature Received!")
        # logging.info("Sync-ing and uploading %s", file_name)

        # send SENDDEL msg 
        msg = pm.get_senddel_msg(client_id,file_name,db_conn)
        client_socket.send(msg)

        signature = tempfile.SpooledTemporaryFile(max_size=MAX_SPOOL, mode='wb+')
        signature.write(sigdata)
        signature.seek(0)
        src = open(file_name, 'rb')
        delta = sync.delta(src,signature)        
        delta.seek(0)
        # connect to delta socket

        client_del_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        wait_net_service(client_del_socket, SERVER_IP ,pm.SharedPort.server_del_port)

        # send delta

        l = delta.read(BUFFER_SIZE)
        while l:
            client_del_socket.send(l)
            l = delta.read(BUFFER_SIZE)
        delta.close()
    
        client_del_socket.close()
        logging.info("Delta Sent!")

        return 1
        
    if msg_code == pm.msgCode.REQSIG:

        # next update : create a data socket to send large signature
        msg = pm.get_sensig_msg(client_id,file_name,db_conn)
        client_socket.send(msg)
        send_signature(file_name)
        
        return 1

    if msg_code == pm.msgCode.SENDDEL:
        
        # receive delta

        del_socket = socket.socket()
        addr = ('', pm.SharedPort.client_del_port)
        del_socket.bind(addr)
        #print "Client del socket is ready at: {}".format(data_socket.getsockname())
        del_socket.listen(10)
        client_del_sock, addr = del_socket.accept()
        
        # Receive Signature
        deldata = ""
        while True:
            data = client_del_sock.recv(BUFFER_SIZE)
            deldata += data
            if not data:
                break
        
        client_del_sock.close()
        del_socket.close()
        
        logging.info("Delta has been received!")

        delta = tempfile.SpooledTemporaryFile(max_size=MAX_SPOOL, mode='wb+')
        delta.write(deldata)
        delta.seek(0)

        ### Ask to Merge 
        ### Hard to produce this case
        ### Happens when both updates are done at a same time instance 
        last_m_time = os.path.getmtime(file_name)
        db_m_time = pm.get_data(db_conn,file_name, "client_m_time")
        
        if last_m_time > db_m_time:
            print "WARNING!"
            print file_name ," has changed since last update. Do you want to merge server's update? [Y|N]"
            print "Local updates will be lost if you select 'Yes'"
            ans = raw_input()
            if ans == 'n' or ans == 'N':
                return 1
        
        
        dest = open(file_name,'rb')
        synced_file = open(file_name,'wb')
        sync.patch(dest,delta,synced_file)      # patch the delta
        synced_file.close()

        # crucial for 2 opens
        tempFiles.append(file_name)
        tempFiles.append(file_name)
        logging.info("Updation Successful for file %s", file_name)

        pm.update_db(db_conn,file_name,"client_m_time",os.path.getmtime(file_name))
        db_conn.commit()
        #send server_m_time to client for update
        ret_msg = pm.get_sendcmt_msg(client_id,file_name,db_conn)
        #logging.info("returning msg for updating SMT: %s",ret_msg)
        client_socket.send(ret_msg)
        return 1


    if msg_code == pm.msgCode.SENDDAT:
        
        #create a new socket and send the data via it
        data_socket = socket.socket()
        addr = ('', C_DATA_SOCK_PORT)
        data_socket.bind(addr)
        #print "Client data socket is ready at: {}".format(data_socket.getsockname())
        data_socket.listen(10)
        client_data_sock, addr = data_socket.accept()
        
        # directory traversing
        # if sub directories do not exist then create accordingly
        subpath = file_name.split('/')
        for i in range(len(subpath)-1):
            dname = subpath[i]
            if dname == '.':
                continue
            if os.path.exists(dname) is False:
                os.mkdir(dname)

        if file_name in locked and locked[file_name] == 1:
            print "CONFLICT : Local copy is currently being modified! Server copy cannot be downloaded!"
            conflict[file_name] = 1
            client_data_sock.close()
            data_socket.close()
            return 0
        
        with open(file_name, 'wb') as f:
            while True:
                data = client_data_sock.recv(BUFFER_SIZE)
                if not data:
                    break
                f.write(data)
            f.close()
        
        tempFiles.append(file_name)
        logging.info("file recieved: %s",file_name)
        client_data_sock.close()
        data_socket.close()

        return 1
        

    if msg_code == pm.msgCode.SREQ:
        # SERVER sync

        if os.path.exists(file_name) is True:
            # if server file exists in the client directory
            s_server_m_time, s_client_m_time = data.split('<##>')
            c_client_m_time = pm.get_data(db_conn,file_name,"client_m_time")
            c_server_m_time = pm.get_data(db_conn,file_name,"server_m_time")

            # print "server: server_m_time ", s_server_m_time, "client_m_time ", s_client_m_time
            # print "client: server_m_time ", c_server_m_time, "client_m_time ", c_client_m_time

            if s_server_m_time > c_server_m_time:
                # server has updated copy
                if file_name in locked and locked[file_name] == 1:
                    print "CONFLICT : Local copy is currently being modified! Server copy cannot be downloaded!"
                    conflict[file_name] = 1
                    return 0
                
                msg = pm.get_sensig_msg(client_id,file_name,db_conn)
                client_socket.send(msg)
                send_signature(file_name)
                return 1
            
            elif s_server_m_time == c_server_m_time:
                # same copy
                msg = pm.get_sendnoc_msg(client_id,file_name,db_conn)
                client_socket.send(msg)
                return 1
            

        else :
            # send a request to send the total file
            logging.info("Requesting File: %s",file_name)
            sm_time, cm_time = data.split('<##>')
            #print "timestamp", sm_time, cm_time
            pm.update_db(db_conn,file_name,"client_m_time",cm_time)
            pm.update_db(db_conn,file_name,"server_m_time",sm_time)
            db_conn.commit()
            msg = pm.get_reqtot_msg(client_id,file_name,db_conn)
            client_socket.send(msg)
            return 1


    if msg_code == pm.msgCode.DELREQ:

        if file_name in locked and locked[file_name] == 1:
            print "CONFLICT : Local copy is currently being modified! Server action cannot be done!"
            delreq[file_name] = 1
            return 0
        
        os.remove(file_name)
        pm.delete_record(db_conn,file_name)
        db_conn.commit()
        tempdelFiles.append(file_name)
        return 0

    if msg_code == pm.msgCode.MVREQ:
        os.rename(data,file_name)
        pm.update_db_filename(db_conn,data,file_name)
        db_conn.commit()
        tempmvFiles.append(file_name)
        return 0

    if msg_code == pm.msgCode.CONFLICT:
        
        print "The ", file_name , " is being accessed by some other client device! Updation is conflictiing"
        return 1    


    if msg_code == pm.msgCode.TERMIN:
        return  0  # close connection

        

def handle_request(client_socket, db_conn):
    ''' request handler for client '''
    
    while True:
        logging.debug("Listening Server: ")
        msglist = client_socket.recv(BUFFER_SIZE)
        if msglist == "":
            return
        for msg in msglist.split(pm.msgCode.endmark):
            if msg == "":
                break
            #logging.debug("msg from server : %s",msg)
            service_message(msg,client_socket,db_conn)
        time.sleep(1)
        

def server_sync(db_conn, client_id, client_socket):
    tempFiles[:] = []   # clear the list

    msg = pm.get_servsync_msg(client_id, '\0', db_conn)
    client_socket.send(msg)
    print "Sync-ing with server... Please wait... This may take a while..."
    # now this becomes a server
    
    #logging.debug("Now lock : {}".format(pm.SharedPort.client_sync_port_used))
    while pm.SharedPort.client_sync_port_used:
        continue

    pm.SharedPort.client_sync_port_used = True
    #logging.debug("Now lock : {}".format(pm.SharedPort.client_sync_port_used))
    

    client_sync_socket = socket.socket()
    addr = ('', pm.SharedPort.client_sync_port)
    client_sync_socket.bind(addr)
    # print "Client Synchronization socket is ready at: {}".format(client_sync_socket.getsockname())
    client_sync_socket.listen(1)
    serv_sock, addr = client_sync_socket.accept()
    ret = 1
    while ret is 1:
        msglist = serv_sock.recv(BUFFER_SIZE)
        if msglist == "":
            continue
        for msg in msglist.split(pm.msgCode.endmark):
            if msg == "":
                break
            #logging.debug("Inside Serversync Daemon: msg from server : %s",msg)
            ret = service_message(msg,serv_sock,db_conn)
    
    #serv_sock.close()
    client_sync_socket.close()
    pm.SharedPort.client_sync_port_used = False
    logging.info("All file synced with server!")
    
    
def updation_on_change(db_conn, client_socket, client_id):
    """
        Inotify Event Listner
    """

    global locked

    print "Notifier started..."
    # add notifier to watch
    notifier = inotify.adapters.InotifyTree('.')
    src_file = None
    dest_file = None
    for event in notifier.event_gen():
        if event is not None:
            (_, type_names, path, filename) = event
            if filename is '' or filename == 'config.db' or filename == 'config.db-journal':
                continue
            if filename and filename[0] == '.': # .goutputstream-ZC9VLZ
                continue
            total_file_name = path + '/' + filename
            print type_names, total_file_name 

            if 'IN_MODIFY' in type_names:

                # currently being modified
                locked[total_file_name] = 1

            if 'IN_CLOSE_WRITE' in type_names:

                # for updation and new creation of files
                locked[total_file_name] = 0
                
                if total_file_name in conflict and conflict[total_file_name] == 1:
                    print "CONFLICT : Server copy of " + total_file_name + " has been modified!"
                    # remove local copy and download the latest server copy
                    print "Server copy is being prioritized"
                    os.remove(total_file_name)
                    msg = pm.get_resend_msg(client_id,total_file_name)
                    pm.delete_record(db_conn,total_file_name)
                    client_socket.send(msg)
                    continue

                if total_file_name in delreq and delreq[total_file_name] == 1:
                    os.remove(total_file_name)
                    pm.delete_record(db_conn,total_file_name)
                    db_conn.commit()
                    tempdelFiles.append(total_file_name)
                    delreq[total_file_name] = 0

                if total_file_name in tempFiles:    # just downloaded or patched files
                    logging.info("%s is just downloaded or patched!", total_file_name)
                    tempFiles.remove(total_file_name)
                    continue
                
                logging.info("sending update to server %s", total_file_name)
                pm.update_db(db_conn,total_file_name,"client_m_time",os.path.getmtime(total_file_name))
                db_conn.commit()
                msg = pm.get_creq_msg(client_id,total_file_name,db_conn)
                client_socket.send(msg)

            if 'IN_DELETE' in type_names:
                
                # for deletion of files

                if total_file_name in conflict and conflict[total_file_name] == 1:
                    conflict[total_file_name] = 0 
                    continue

                if total_file_name in tempdelFiles:
                    tempdelFiles.remove(total_file_name)
                    continue

                pm.delete_record(db_conn,total_file_name)
                db_conn.commit()
                logging.info("Deleting file %s", total_file_name)
                msg = pm.get_delreq_msg(client_id,total_file_name,db_conn)
                client_socket.send(msg)
                

            if 'IN_MOVED_FROM' in type_names:

                src_file = total_file_name
            
            if 'IN_MOVED_TO' in type_names:
                
                dest_file = total_file_name
                if total_file_name in tempmvFiles:
                    tempmvFiles.remove(total_file_name)
                    continue

                if src_file is None:
                    continue

                pm.update_db_filename(db_conn, src_file, dest_file)
                db_conn.commit()
                logging.info("Renaming filename %s to %s", src_file, total_file_name)
                msg = pm.get_mvreq_msg(client_id,total_file_name,src_file,db_conn)
                client_socket.send(msg)
                src_file = None
                dest_file = None

        time.sleep(1)


def _main():
    
    global tempFiles, tempdelFiles, tempmvFiles

    if len(sys.argv) != 5:
        print USAGE_MESG
        exit(0)

    client_id = sys.argv[4]
    directory = sys.argv[1]
    SERVER_IP = sys.argv[2]
    SERVER_PORT = int(sys.argv[3])
    os.chdir(directory)
    db_conn = pm.open_db()
    pm.create_table(db_conn)

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = (SERVER_IP,SERVER_PORT)
    print "connecting to Pocket File Server {}".format(server_address)
    client_socket.connect(server_address)

    print "[+] Connected to Pocket File Server."

    try:
        #sync serverfiles
        server_sync(db_conn, client_id, client_socket)

        client_listener = thread.start_new_thread(handle_request, (client_socket,db_conn))
        notifier_listener = thread.start_new_thread(updation_on_change(db_conn,client_socket,client_id))
                    
        # client_listener.join()
        # notifier_listener.join()

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
        traceback.print_exc()
    #finally:
        #client_socket.send("END")
        #client_socket.close()


if __name__ == "__main__":
    _main()