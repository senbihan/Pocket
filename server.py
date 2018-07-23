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
active_clients = []
client_dict = {}


logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(message)s')

def wait_net_service(s, server, port, timeout=None):
    """ Wait for network service to appear 
        @param timeout: in seconds, if None or 0 wait forever
        @return: True of False, if timeout is None may return only True or
                 throw unhandled network exception
    """
    import errno

    # s = socket.socket()
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
            #s.close()
            return True


def send_signature(client_id, ip, file_name, db_conn, client):

    msg = pm.get_sensig_msg(client_id,file_name,db_conn)
    client.send(msg)

    # connect for sync
    server_sig_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    wait_net_service(server_sig_socket, ip,pm.SharedPort.client_sig_port)

    # calculate signature
    sig = sync.signature(open(file_name,"rb+"))

    # logging.info("sending signature of file : %s",file_name)
    
    l = sig.read(BUFFER_SIZE)
    while l:
        server_sig_socket.send(l)
        l = sig.read(BUFFER_SIZE)
    sig.close()
    server_sig_socket.close()
    
    logging.info("Signature Sent!")


def recieve_delta_and_patch(file_name):

    # receive delta
    del_socket = socket.socket()
    address = ('', pm.SharedPort.server_del_port)
    del_socket.bind(address)
    #print "Client del socket is ready at: {}".format(data_socket.getsockname())
    del_socket.listen(10)
    client_del_sock, addr = del_socket.accept()
    
    # Receive delta
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
    dest = open(file_name,'rb')
    synced_file = open(file_name,'wb')
    sync.patch(dest,delta,synced_file)      # patch the delta
    synced_file.close()
    
    logging.info("Updation Successful for file %s",file_name)


def recieve_signature_and_send_delta(client_id, client, ip, file_name, db_conn):

    sig_socket = socket.socket()
    address = ('', pm.SharedPort.server_sig_port)
    sig_socket.bind(address)
    #print "Client sig socket is ready at: {}".format(data_socket.getsockname())
    sig_socket.listen(10)
    client_sig_sock, addr = sig_socket.accept()
    
    # Receive Signature
    sigdata = ""
    while True:
        data = client_sig_sock.recv(BUFFER_SIZE)
        sigdata += data
        if not data:
            break
    
    client_sig_sock.close()
    sig_socket.close()
    
    logging.info("Signature Received!")
    # logging.info("Sync-ing and uploading %s", file_name)

    # send SENDDEL msg 
    msg = pm.get_senddel_msg(client_id,file_name,db_conn)
    client.send(msg)

    #calculate delta
    signature = tempfile.SpooledTemporaryFile(max_size=MAX_SPOOL, mode='wb+')
    signature.write(sigdata)
    signature.seek(0)
    src = open(file_name, 'rb')
    delta = sync.delta(src,signature)        
    
    # connect to delta socket

    client_del_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    wait_net_service(client_del_socket, ip ,pm.SharedPort.client_del_port)

    # send delta

    l = delta.read(BUFFER_SIZE)
    while l:
        client_del_socket.send(l)
        l = delta.read(BUFFER_SIZE)
    delta.close()

    client_del_socket.close()
    logging.info("Delta Sent!")




def service_message(msg, client, addr, db_conn, flag):
    '''
        Service msg as obtained from the client
    '''
    global sh_completed, active_clients, client_dict

    msg_code, client_id, file_name, data = msg.split(pm.msgCode.delim)
    client_dict[client] = client_id
    #print msg_code, client_id, file_name, data
    #print "name of ", client , "is ", client_id, " dict value: ", client_dict[client]

    if msg_code == pm.msgCode.CREQ:
        # request to sync
        if os.path.exists(file_name) is True:

            c_server_m_time, c_client_m_time = data.split('<##>')
            
            s_client_m_time = pm.get_data(db_conn,file_name,"client_m_time")
            s_server_m_time = pm.get_data(db_conn,file_name,"server_m_time")

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
                        logging.info("Requesting Update for file : %s from client: %s",file_name,client_id)
                        pm.update_db(db_conn,file_name,"client_m_time",c_client_m_time)
                        db_conn.commit()
                        send_signature(client_id, addr[0], file_name, db_conn, client)
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
                    logging.info("Sending Update for file : %s to client %s",file_name, client_id)
                    msg = pm.get_reqsig_msg(client_id,file_name,db_conn)
                    client.send(msg)
                    return 1

                if c_client_m_time > s_client_m_time:
                    # SENDSIG Sig
                    logging.info("Requesting Update for file : %s from client: %s",file_name,client_id)
                    pm.update_db(db_conn,file_name,"client_m_time",c_client_m_time)
                    db_conn.commit()
                    send_signature(client_id, addr[0], file_name, db_conn, client)
                    return 1

                elif c_client_m_time < s_client_m_time:

                    #REQSIG msg
                    logging.info("Sending Update for file : %s to client %s",file_name, client_id)
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
        header = pm.get_senddat_msg(client_id,file_name, db_conn)
        client.send(header)
        #logging.debug("SENDDAT msg sent")
        # time.sleep(1)           # wait for client data socket to be ready
        # now server sends the total file to client
        server_data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        wait_net_service(server_data_socket, addr[0],C_DATA_SOCK_PORT)
        #server_data_socket.connect(client_data_address)
        #logging.debug("connected!")

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
        
        recieve_delta_and_patch(file_name)
        # necessary database updates
        pm.update_db(db_conn,file_name,"server_m_time",os.path.getmtime(file_name))
        db_conn.commit()
        #send server_m_time to client for update
        ret_msg = pm.get_sendsmt_msg(client_id,file_name,db_conn)
        #logging.info("returning msg for updating SMT: %s",ret_msg)
        client.send(ret_msg)

        
        #print active_clients
        #print client_dict
        for acclients in active_clients:
            if acclients != client and client_id != client_dict[acclients]:
                #logging.debug("sending SREQ to client %s",client_dict[acclients])
                msg = pm.get_sreq_msg(client_dict[acclients],file_name,db_conn)
                acclients.send(msg)

        return 1
    
    if msg_code == pm.msgCode.SENDDAT: 
        
        #create a new socket and send the data via it
        
        while pm.SharedPort.server_port_used:
            continue
        
        pm.SharedPort.server_port_used = True

        data_socket = socket.socket()
        address = ('', S_DATA_SOCK_PORT)
        data_socket.bind(address)
        #print "Server data socket is ready at: {}".format(data_socket.getsockname())
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

        #print active_clients
        #print client_dict
        for acclients in active_clients:
            if acclients != client and client_id != client_dict[acclients]:
                #logging.debug("sending SREQ to client %s",client_dict[acclients])
                msg = pm.get_sreq_msg(client_dict[acclients],file_name,db_conn)
                acclients.send(msg)
        

        return 1

    if msg_code == pm.msgCode.SENDSIG:

        recieve_signature_and_send_delta(client_id, client, addr[0], file_name, db_conn)
        return 1

    if msg_code == pm.msgCode.SENDCMT:
        #logging.info("updating cmt")
        pm.update_db(db_conn,file_name,"client_m_time",data)
        db_conn.commit()

        if flag:
            return 0
        return 1    

    if msg_code == pm.msgCode.SENDNOC:
        
        sh_completed += 1
        return 0
    
    if msg_code == pm.msgCode.RESEND:

        msg = pm.get_sreq_msg(client_id,file_name,db_conn)
        client.send(msg)
        
        return 1
        

    if msg_code == pm.msgCode.DELREQ:

        if os.path.exists(file_name):
            os.remove(file_name)
            pm.delete_record(db_conn,file_name)
            db_conn.commit()
            for acclients in active_clients:
                if acclients is not client:
                    msg = pm.get_delreq_msg(client_dict[acclients],file_name,db_conn)
                    acclients.send(msg)
            
        return 1

    if msg_code == pm.msgCode.MVREQ:
        
        # data = old file name
        if os.path.exists(data):
            os.rename(data,file_name)
            pm.update_db_filename(db_conn,data,file_name)
            db_conn.commit()
            for acclients in active_clients:
                if acclients is not client:
                    msg = pm.get_mvreq_msg(client_dict[acclients],file_name,data,db_conn)
                    acclients.send(msg)
        
        return 1

    

    if msg_code == pm.msgCode.SERVSYNC:
        
        # sync all server files with client
        file_name_list = []
        for dirpath, dirnames, filenames in os.walk('.'):
            for filename in filenames:
                if filename == "config.db":
                    continue
                fname = dirpath + '/' + filename
                file_name_list.append(fname)
        

        server_sync_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_address = (addr[0],pm.SharedPort.client_sync_port)
        wait_net_service(server_sync_socket, addr[0],pm.SharedPort.client_sync_port, 5)
        # print "connecting to Client Synchroniztion {}".format(client_address)
        #server_sync_socket.connect(client_address)

        if len(file_name_list) == 0:
            termsg = pm.get_terminate_msg(client_id,'',db_conn)
            server_sync_socket.send(termsg)

        for file_name in file_name_list:
            msg = pm.get_sreq_msg(client_id,file_name,db_conn)
            server_sync_socket.send(msg)
        
            handle_request(server_sync_socket,addr,db_conn, True)
        

        logging.info("All file synced with client %s!",client_id)
        termsg = pm.get_terminate_msg(client_id,'',db_conn)
        server_sync_socket.send(termsg)

        server_sync_socket.close()

        return 1




def handle_request(client, addr, db_conn, flag = False):
    ret = 1
    global active_clients
    while ret == 1:
        msgList = client.recv(BUFFER_SIZE)
        if msgList == "":
            continue
        #logging.debug("msglist : %s",msgList)
        for msg in msgList.split(pm.msgCode.endmark):
            if msg == "":
                continue            
            #logging.info("recieved msg: %s",msg)
            ret = service_message(msg, client, addr, db_conn, flag)
        
        time.sleep(0.5)
    
    if flag is False:   # main thread
        client.close()
        active_clients.remove(client)        

def _main():

    global active_clients
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
        if client not in active_clients:
            active_clients.append(client)
        logging.info("[+] getting connection from %s",addr)
        thread.start_new_thread(handle_request,(client,addr,db_conn, False))
    
    server.close()


if __name__ == "__main__":
    _main()