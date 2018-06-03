import sys
import os
import socket
import getpass
import inotify.adapters
import time
import pocketmsg as pm
import logging
import traceback

BUFFER_SIZE     =   200
SERVER_IP       =   ''
USAGE_MESG      = '''Pocket : A simple fileserver synced with your local directories

usage : python client.py [path to the directory]
'''
client_id = ''
logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(message)s')


def service_message(msg, client_socket, db_conn):

    if db_conn is None:
        db_conn = pm.open_db()

    msg_code, client_id, file_name, data = msg.split('|#|')

    if msg_code == pm.msgCode.REQTOT:
        header = pm.get_senddat_header(client_id,file_name, db_conn)
        logging.info("sending : header = %s", header)
        client_socket.send(header)
        logging.debug("opening file : %s",file_name)
        f = open(file_name, 'rb')
        l = f.read(BUFFER_SIZE)
        while l:
            client_socket.send(header + str(l))
            l = f.read(BUFFER_SIZE)
        f.close()
        logging.debug("file sent: %s", file_name)
        time.sleep(10)


def _main():
    
    if len(sys.argv) != 4:
        print USAGE_MESG
        exit(0)

    client_id = raw_input("Client ID: ")
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
        #sync to the server
        #update client_m_time 
        file_name_list = []
        for dirpath, dirnames, filenames in os.walk('.'):
            for filename in filenames:
                if filename == "config.db":
                    continue
                fname = dirpath + '/' + filename
                logging.info("updating client_m_time of %s" , fname)
                ret = pm.update_db(db_conn,fname,"client_m_time",os.path.getmtime(fname))
                db_conn.commit()
                logging.info("updating: %s" , ret)
                if ret == 1:
                    file_name_list.append(fname)
                #pm.show_data(db_conn)
                #send creq msg
        

        for file_name in file_name_list:
            msg = pm.get_creq_msg(client_id,file_name,db_conn)
            client_socket.send(msg)
            time.sleep(5)
        
        while True:
            msg = client_socket.recv(BUFFER_SIZE)
            if msg is "":
                continue
            logging.debug("msg from server : %s",msg)
            service_message(msg,client_socket,db_conn)
            # add notifier to watch
            #notifier = inotify.adapters.InotifyTree(directory)
            #events = list(i.event_gen(yield_nones=False, timeout_s=1))
            #print(events)

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