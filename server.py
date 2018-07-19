import sys
import socket
from threading import Thread
import thread
import pocketmsg as pm
import os
import logging
import time
import traceback
import librsync as sync
import tempfile


sh_completed = 0
MAX_SPOOL = 1024 ** 2 * 5
BUFFER_SIZE =  1024
C_DATA_SOCK_PORT = pm.SharedPort.client_port
S_DATA_SOCK_PORT = pm.SharedPort.server_port
logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(message)s')



def service_message(msg, client, addr, db_conn, flag):
    '''
        Service msg as obtained from the client
    '''
    global sh_completed

    msg_code, client_id, file_name, data = msg.split(pm.msgCode.delim)
    #print msg_code, client_id, file_name, data
    
    if msg_code == pm.msgCode.CREQ:
        # request to sync
        if os.path.exists(file_name) is True:

            c_server_m_time, c_client_m_time = data.split('<##>')
            
            # for test purposes only. server db updation only occurs when some file updated by any client
            # assuming server is running indefinitely
            # pm.update_db(db_conn,file_name,"server_m_time",os.path.getmtime(file_name))
            # db_conn.commit()
            
            s_client_m_time = pm.get_data(db_conn,file_name,"client_m_time")
            s_server_m_time = pm.get_data(db_conn,file_name,"server_m_time")

            #print "server: server_m_time ", s_server_m_time, "client_m_time ", s_client_m_time
            #print "client: server_m_time ", c_server_m_time, "client_m_time ", c_client_m_time
            
            #Case 1
            if s_server_m_time == c_server_m_time:
                # server upddate time of both the file are same
                if s_client_m_time == c_client_m_time:
                    # No update
                    return 1
                else:

                    if c_client_m_time > s_client_m_time:
                        # present client has more updated data 
                        # SENDSIG Sig
                        logging.info("Requesting Update for file : %s",file_name)
                        msg = pm.get_sensig_msg(client_id,file_name,db_conn)
                        #logging.info("sending signature of file : %s",file_name)
                        pm.update_db(db_conn,file_name,"client_m_time",c_client_m_time)
                        db_conn.commit()
                        client.send(msg)
                        return 1
                    else:
                        # CONFLICT
                        # [doubt]
                        msg = pm.get_conflict_msg(client_id,file_name, db_conn)
                        client.send(msg)
                        return 1
            else:                               
                # The requesting client is not synced with server
                if c_client_m_time == s_client_m_time:
                    #REQSIG msg
                    logging.info("Sending Update for file : %s",file_name)
                    msg = pm.get_reqsig_msg(client_id,file_name,db_conn)
                    client.send(msg)
                    return 1

                if c_client_m_time > s_client_m_time:
                    # SENDSIG Sig
                    logging.info("Requesting Update for file : %s",file_name)
                    msg = pm.get_sensig_msg(client_id,file_name,db_conn)
                    #logging.info("sending signature of file : %s",file_name)
                    pm.update_db(db_conn,file_name,"client_m_time",c_client_m_time)
                    db_conn.commit()
                    client.send(msg)
                    return 1

                elif c_client_m_time < s_client_m_time:
                    #REQSIG msg
                    logging.info("Sending Update for file : %s",file_name)
                    msg = pm.get_reqsig_msg(client_id,file_name,db_conn)
                    client.send(msg)
                    return 1
                
                                
        else :
            # send a request to send the total file
            logging.info("Requesting File: %s",file_name)
            sm_time, cm_time = data.split('<##>')
            pm.update_db(db_conn,file_name,"client_m_time",cm_time)
            db_conn.commit()
            ret_msg = pm.get_reqtot_msg(client_id,file_name,db_conn)
            #logging.info("returing msg for requesting data: %s",ret_msg)
            client.send(ret_msg)
            #time.sleep(5) 
            return 1 

    if msg_code == pm.msgCode.REQTOT:
        header = pm.get_senddat_header(client_id,file_name, db_conn)
        client.send(header + pm.msgCode.endmark)

        time.sleep(10)           # wait for client data socket to be ready
        # now server sends the total file to client
        server_data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_data_address = (addr[0], C_DATA_SOCK_PORT)
        print client_data_address
        server_data_socket.connect(client_data_address)
        #logging.debug("opening file : %s",file_name)
        with open(file_name, 'rb') as f:
            l = f.read(BUFFER_SIZE)
            while l:
                server_data_socket.send(l)
                l = f.read(BUFFER_SIZE)
            f.close()
        logging.debug("file sent: %s", file_name)
        server_data_socket.close()
        
        if flag:
            return 0
        return 1 

    if msg_code == pm.msgCode.SENDDEL:
        # received delta
        delta = tempfile.SpooledTemporaryFile(max_size=MAX_SPOOL, mode='wb+')
        delta.write(data)
        delta.seek(0)
        dest = open(file_name,'rb')
        synced_file = open(file_name,'wb')
        sync.patch(dest,delta,synced_file)      # patch the delta
        synced_file.close()
        print "Updation Successful"

        pm.update_db(db_conn,file_name,"server_m_time",os.path.getmtime(file_name))
        db_conn.commit()
        #send server_m_time to client for update
        ret_msg = pm.get_sendsmt_msg(client_id,file_name,db_conn)
        #logging.info("returning msg for updating SMT: %s",ret_msg)
        client.send(ret_msg)
        return 1
    
    if msg_code == pm.msgCode.SENDDAT:
        
        #create a new socket and send the data via it
        
        while pm.SharedPort.server_port_used:
            continue
        
        pm.SharedPort.server_port_used = True

        data_socket = socket.socket()
        addr = ('', S_DATA_SOCK_PORT)
        data_socket.bind(addr)
        print "Server data socket is ready at: {}".format(data_socket.getsockname())
        data_socket.listen(10)
        client_data_sock, addr = data_socket.accept()
        with open(file_name, 'wb') as f:
            while True:
                data = client_data_sock.recv(BUFFER_SIZE)
                if not data:
                    break
                f.write(data)
            f.close()
        logging.info("file recieved: %s",file_name)
        data_socket.close()
        pm.SharedPort.server_port_used = False

        #update server_m_time
        ret = pm.update_db(db_conn,file_name,"server_m_time",os.path.getmtime(file_name))
        db_conn.commit()
        #send server_m_time to client for update
        ret_msg = pm.get_sendsmt_msg(client_id,file_name,db_conn)
        #logging.info("returning msg for updating SMT:")
        client.send(ret_msg)
        return 1

    if msg_code == pm.msgCode.SENDSIG:
        #compute delta and send
        #logging.info("Sync-ing and sending %s", file_name)
        msg = pm.get_senddel_msg(client_id,file_name,data,db_conn)
        client.send(msg)
        return 1

    if msg_code == pm.msgCode.SENDCMT:
        logging.info("updating cmt")
        pm.update_db(db_conn,file_name,"client_m_time",data)
        db_conn.commit()

        if flag:
            return 0
        return 1    

    if msg_code == pm.msgCode.SENDNOC:
        
        sh_completed += 1
        return 0
    
    if msg_code == pm.msgCode.SERVSYNC:
        
        # sync all server files with client
        file_name_list = []
        for dirpath, dirnames, filenames in os.walk('.'):
            for filename in filenames:
                if filename == "config.db":
                    continue
                fname = dirpath + '/' + filename
                file_name_list.append(fname)

        
        time.sleep(5)       # wait for client to be ready

        server_sync_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_address = (addr[0],pm.SharedPort.client_sync_port)
        print "connecting to Client Synchroniztion {}".format(client_address)
        server_sync_socket.connect(client_address)

        if len(file_name_list) == 0:
            termsg = pm.get_terminate_msg(client_id,'',db_conn)
            server_sync_socket.send(termsg)
            return 1

        for file_name in file_name_list:
            msg = pm.get_sreq_msg(client_id,file_name,db_conn)
            print "sending", msg
            server_sync_socket.send(msg)
        
            handle_request(server_sync_socket,addr,db_conn, True)
        

        logging.info("All file synced!")
        server_sync_socket.close()

        return 1




def handle_request(client, addr, db_conn, flag = False):
    ret = 1
    while ret == 1:
        msgList = client.recv(BUFFER_SIZE)
        if msgList == "":
            continue
        #logging.debug("msglist : %s",msgList)
        for msg in msgList.split(pm.msgCode.endmark):
            if msg == "":
                continue            
            logging.info("recieved msg: %s",msg)
            ret = service_message(msg, client, addr, db_conn, flag)
    
    client.close()        

def _main():
    # create a server socket
    if len(sys.argv) != 2:
        print "usage: python server.py [dirname]"    
    os.chdir(sys.argv[1])
    server = socket.socket()
    addr = ('', 0)
    server.bind(addr)
    print "Pocket Server Started at : {}".format(server.getsockname())
    db_conn = pm.open_db()
    pm.create_table(db_conn)
    server.listen(20)

    # CLIENT SYNC (both for Online and Newly connected Client)
    threads = []
    while True:
        client, addr = server.accept()
        logging.info("[+] getting connection from %s",addr)
        thread.start_new_thread(handle_request,(client,addr,db_conn))
    
    server.close()


if __name__ == "__main__":
    _main()