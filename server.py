import sys
import socket
from threading import Thread
import thread
import pocketmsg as pm
import os
import logging
import time

BUFFER_SIZE =  1024
DATA_SOCK_PORT  =  54321
locked = {}
recieve_file_flag = False
logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(message)s')

def service_message(msg, client, db_conn):
    
    msg_code, client_id, file_name, data = msg.split(pm.msgCode.delim)
    print msg_code, client_id, file_name, data
    if msg_code == pm.msgCode.CREQ:
        # request to connection and sync
        if os.path.exists(file_name) is True:
            pass
        else :
            # send a request to send the total file
            sm_time, cm_time = data.split('<##>')
            pm.update_db(db_conn,file_name,"client_m_time",cm_time)
            db_conn.commit()
            ret_msg = pm.get_reqtot_msg(client_id,file_name,db_conn)
            logging.info("returing msg for requesting data: %s",ret_msg)
            client.send(ret_msg)
            time.sleep(5)  
    
    if msg_code == pm.msgCode.SENDDAT:
        
        #create a new socket and send the data via it
        data_socket = socket.socket()
        addr = ('', DATA_SOCK_PORT)
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

        #update server_m_time
        ret = pm.update_db(db_conn,file_name,"server_m_time",os.path.getmtime(file_name))
        db_conn.commit()
        #send server_m_time to client for update
        ret_msg = pm.get_sendsmt_msg(client_id,file_name,db_conn)
        logging.info("returing msg for requesting data: %s",ret_msg)
        client.send(ret_msg)
        time.sleep(5)  
    


def handle_request(client, addr, db_conn):
    while True:
        msgList = client.recv(BUFFER_SIZE)
        if msgList == "":
            continue
        logging.debug("msglist : %s",msgList)
        for msg in msgList.split(pm.msgCode.endmark):
            if msg == "":
                continue            
            logging.info("recieved msg: %s",msg)
            service_message(msg, client, db_conn)
        
    client.close()

def _main():
    # create a server socket
    if len(sys.argv) != 2:
        print "usage: python server.py [dirname]"
    server = socket.socket()
    addr = ('', 0)
    server.bind(addr)
    print "Pocket Server Started at : {}".format(server.getsockname())
    server.listen(5)

    os.chdir(sys.argv[1])
    db_conn = pm.open_db()
    pm.create_table(db_conn)

    threads = []
    while True:
        client, addr = server.accept()
        logging.info("getting connection from %s",addr)
        t = Thread(handle_request(client,addr,db_conn))
        threads.append(t)
        t.start()
        time.sleep(10)
        

    server.close()


if __name__ == "__main__":
    _main()