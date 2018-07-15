import sys
import os
import socket
import getpass
import inotify.adapters
import time
import pocketmsg as pm
import logging
import traceback
from threading import Thread
import librsync as sync
import tempfile


BUFFER_SIZE     =   1024
MAX_SPOOL       =   1024 ** 2 * 5
SERVER_IP       =   ''
C_DATA_SOCK_PORT  =  54322
S_DATA_SOCK_PORT  =  54321
USAGE_MESG      = '''Pocket : A simple fileserver synced with your local directories

usage : python client.py [path to the directory]
'''
client_id = ''
logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(message)s')


def service_message(msg, client_socket, db_conn):

    if db_conn is None:
        db_conn = pm.open_db()

    msg_code, client_id, file_name, data = msg.split(pm.msgCode.delim)

    if msg_code == pm.msgCode.REQTOT:
        header = pm.get_senddat_header(client_id,file_name, db_conn)
        #logging.info("sending : header = %s", header)
        client_socket.send(header + pm.msgCode.endmark)

        time.sleep(10)           # wait for server data socket to be ready
        client_data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_data_address = (SERVER_IP,S_DATA_SOCK_PORT)
        client_data_socket.connect(server_data_address)
        #logging.debug("opening file : %s",file_name)
        with open(file_name, 'rb') as f:
            l = f.read(1000)
            while l:
                client_data_socket.send(l)
                l = f.read(1000)
            f.close()
        logging.debug("file sent: %s", file_name)
        client_data_socket.close()
        time.sleep(2)
        return 0

    if msg_code == pm.msgCode.SENDSMT:
        #logging.info("updating server_m_time of %s to %s",file_name,data)
        pm.update_db(db_conn,file_name,"server_m_time",data)
        db_conn.commit()
        #pm.show_data(db_conn)

        return 0    #   close connection

    if msg_code == pm.msgCode.SENDSIG:
        #compute delta and send
        logging.info("Sync-ing and uploading %s", file_name)
        msg = pm.get_senddel_msg(client_id,file_name,data,db_conn)
        #print "delta: ", msg
        client_socket.send(msg)
        return 1

    if msg_code == pm.msgCode.REQSIG:

        msg = pm.get_sensig_msg(client_id,file_name,db_conn)
        client_socket.send(msg)
        return 1
    

    if msg_code == pm.msgCode.SENDDEL:
        # received delta
        delta = tempfile.SpooledTemporaryFile(max_size=MAX_SPOOL, mode='wb+')
        delta.write(data)
        delta.seek(0)

        ### Ask to Merge !!?
        last_m_time = os.path.getmtime(file_name)
        db_m_time = pm.get_data(db_conn,file_name, "client_m_time")
        
        if last_m_time > db_m_time:
            print "WARNING!"
            print file_name ," has changed since last update. Do you want to merge server's update? [Y|N]"
            print "Local updates will be lost if you select 'Yes'"
            ans = raw_input()
            if ans == 'n' or ans == 'N':
                return 0
         
        dest = open(file_name,'rb')
        synced_file = open(file_name,'wb')
        sync.patch(dest,delta,synced_file)      # patch the delta
        synced_file.close()
        print file_name, "Updation Successful"

        #print "SERVER M TIME : ", os.path.getmtime(file_name)
        pm.update_db(db_conn,file_name,"client_m_time",os.path.getmtime(file_name))
        db_conn.commit()
        #send server_m_time to client for update
        ret_msg = pm.get_sendcmt_msg(client_id,file_name,db_conn)
        #logging.info("returning msg for updating SMT: %s",ret_msg)
        client_socket.send(ret_msg)
        return 0    #   close connection


    if msg_code == pm.msgCode.SENDDAT:
        
        #create a new socket and send the data via it
        data_socket = socket.socket()
        addr = ('', C_DATA_SOCK_PORT)
        data_socket.bind(addr)
        print "Data socket is ready at: {}".format(data_socket.getsockname())
        data_socket.listen(1)
        client_data_sock, addr = data_socket.accept()
        with open(file_name, 'wb') as f:
            while True:
                data = client_data_sock.recv(1000)
                if not data:
                    break
                f.write(data)
            f.close()
        logging.info("file recieved: %s",file_name)
        data_socket.close()


    if msg_code == pm.msgCode.SREQ:
        # SERVER sync

        if os.path.exists(file_name) is True:
            # if server file exists in the client directory
                
            c_server_m_time, c_client_m_time = data.split('<##>')
            s_client_m_time = pm.get_data(db_conn,file_name,"client_m_time")
            s_server_m_time = pm.get_data(db_conn,file_name,"server_m_time")

            # print "server: server_m_time ", s_server_m_time, "client_m_time ", s_client_m_time
            # print "client: server_m_time ", c_server_m_time, "client_m_time ", c_client_m_time

            if s_server_m_time > c_server_m_time:
                # server has updated copy
                msg = pm.get_sensig_msg(client_id,file_name,db_conn)
                client_socket.send(msg)
                return 1

        else :
            # send a request to send the total file
            logging.info("Requesting File: %s",file_name)
            sm_time, cm_time = data.split('<##>')
            pm.update_db(db_conn,file_name,"client_m_time",cm_time)
            pm.update_db(db_conn,file_name,"server_m_time",sm_time)
            db_conn.commit()
            ret_msg = pm.get_reqtot_msg(client_id,file_name,db_conn)
            client_socket.send(ret_msg)
            return 1 



    if msg_code == pm.msgCode.CONFLICT:
        
        print "The ", file_name , " is being accessed by some other client device! Updation is conflictiing"
        return 0    #   close connection


    if msg_code == pm.msgCode.TERMIN:
        return 0    # close connection




def handle_request(client_socket, db_conn):
    ''' request handler for client '''
    ret = 1
    while ret is 1:
        msglist = client_socket.recv(BUFFER_SIZE)
        if msglist == "":
            continue
        for msg in msglist.split(pm.msgCode.endmark):
            if msg == "":
                break
            #logging.debug("msg from server : %s",msg)
            ret = service_message(msg,client_socket,db_conn)
    
    #client_socket.close()

def _main():
    
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


    try:
        #sync serverfiles
        print "Sync-ing with server... Please wait... This may take a while..."
        msg = pm.get_servsync_msg(client_id, '\0', db_conn)
        client_socket.send(msg)
        handle_request(client_socket,db_conn)
        

        #sync client files to the server
        file_name_list = []
        for dirpath, dirnames, filenames in os.walk('.'):
            for filename in filenames:
                if filename == "config.db":
                    continue
                fname = dirpath + '/' + filename
                #logging.info("updating client_m_time of %s" , fname)
                ret = pm.update_db(db_conn,fname,"client_m_time",os.path.getmtime(fname))
                db_conn.commit()
                #logging.info("updating: %s" , ret)
                #if ret == 1:
                file_name_list.append(fname)
                #pm.show_data(db_conn)
                #send creq msg


        # Client Sync
        threads = []
        for file_name in file_name_list:
            print file_name
            msg = pm.get_creq_msg(client_id,file_name,db_conn)
            #logging.info("sending : %s",msg)
            client_socket.send(msg)
            t = Thread(handle_request(client_socket,db_conn))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()

        print "Notifier started..."
        while True:
            #add notifier to watch
            notifier = inotify.adapters.InotifyTree('.')
            #notifier.add_watch('.')
            for event in notifier.event_gen():
                if event is not None:
                    (_, type_names, path, filename) = event
                    if filename is '' or filename == 'config.db':
                        continue
                    

            

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