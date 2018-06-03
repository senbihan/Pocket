import sys
import socket
from threading import Thread
import thread
import pocketmsg as pm
import os
import logging
import time

BUFFER_SIZE =  200
locked = {}
logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(message)s')

def service_message(msg, client, db_conn):
    
    msg_code, client_id, file_name, data = msg.split('|#|')
    print msg_code, client_id, file_name, data
    if msg_code == pm.msgCode.CREQ:
        # request to connection and sync
        if os.path.exists(file_name) is True:
            pass
        else :
            # send a request to send the total file
            ret_msg = pm.get_reqtot_msg(client_id,file_name,db_conn)
            logging.info("ret msg: %s",ret_msg)
            client.send(ret_msg)
            time.sleep(5)  
    
    if msg_code == pm.msgCode.SENDDAT:
        # blocking (high priority)
        if locked.has_key(file_name):
            print "val", locked[file_name]
            if locked[file_name] != client_id:
                time.sleep(50)
            else:
                logging.debug("waiting for file: %s",file_name)
                with open(file_name, 'ab') as f:
                    f.write(data)
                print "closing...file"
                f.close()
                #msg = pm.get_terminate_ft_msg(client_id,file_name,db_conn)
                #logging.debug("sending terminate msg: %s", msg)
                #client.send(msg)
                logging.debug("file receievd: %s", file_name)
                locked[file_name] = 0
        else:
            logging.debug("updating locked info of %s",file_name)
            locked[file_name] = client_id
        

def handle_request(client, addr, db_conn):
    while True:
        msg = client.recv(BUFFER_SIZE)
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
        logging.info("getting connection from % s",addr)
        t = Thread(handle_request(client,addr,db_conn))
        t.start()
        time.sleep(10)
        threads.append(t)
        
    server.close()


if __name__ == "__main__":
    _main()