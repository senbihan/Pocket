import sys
import os
import socket
import getpass
import inotify.adapters
import time
import pocketmsg as pm

SERVER_IP       =   ''
USAGE_MESG      = '''Pocket : A simple fileserver synced with your local directories

usage : python client.py [path to the directory]
'''

def handle_server_request(msg):

    msg_code, client_id, file_name, data = msg.split('|#|')

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
                print "updating client_m_time of " , fname
                ret = pm.update_db(db_conn,fname,"client_m_time",os.path.getmtime(fname))
                db_conn.commit()
                print "updating: " , ret
                if ret == 1:
                    file_name_list.append(fname)
                #pm.show_data(db_conn)
                #send creq msg
        

        for file_name in file_name_list:
            print "sending for ", file_name
            msg = pm.get_creq_msg(client_id,file_name,db_conn)
            print "msg is ", msg
            client_socket.sendall(msg)
        
        while True:
            msg = client_socket.recv(200)
            if msg == "":
                continue
            handle_server_request(msg)
            # add notifier to watch
            #notifier = inotify.adapters.InotifyTree(directory)
            #events = list(i.event_gen(yield_nones=False, timeout_s=1))
            #print(events)

    except:
        print "EXCEPT BLOCK"
    #finally:
        #client_socket.sendall("END")
        #client_socket.close()


if __name__ == "__main__":
    _main()