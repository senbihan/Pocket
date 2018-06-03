import sqlite3 as sq
import os


def open_db():
    ''' Open the client configuration database.
        If not present, creates a new one. '''
        
    conn = sq.connect("config.db", isolation_level=None)
    print "Database opened successfully!" 
    return conn

def create_table(conn):
    ''' create the table trans '''
    
    try:
        conn.execute('''CREATE TABLE trans
            (FILE_ID        CHAR(10) PRIMARY KEY NOT NULL,
            SERVER_M_TIME   REAL,
            CLIENT_M_TIME   REAL);''')
        conn.commit()
    except:
        print "table already exists!"


def insert_db(conn, data):
    ''' data is tuple with fileid, server_m_time, client_m_time
        inserts data into trans table'''
    print "inserting ", data
    try:
        conn.execute("INSERT INTO trans VALUES(?,?,?)", data)
    except:
        print "insertion failed"

def update_db(conn, fileid, key, val):
    '''update field by fileid '''

    data = (val,fileid)
    if key is "client_m_time":
        ldata = (fileid,"NULL",val)
        fdata = (fileid,)
        ret_cur = conn.execute("select client_m_time from trans where file_id = ?",fdata)
        ret = ret_cur.fetchall()
        if len(ret) == 0:
            conn.execute("insert into trans values(?,?,?)",ldata)
            conn.commit()
            return 1
        ret_val = ret[0][0] 
        if val > ret_val or ret_val == "NULL":
            conn.execute("update trans set client_m_time = ? where file_id = ?",data)
            conn.commit()
            return 1
        
        return 0
    
    elif key is "server_m_time":
        ldata = (fileid,val,"NULL",)
        fdata = (fileid,)
        ret_cur = conn.execute("select server_m_time from trans where file_id = ?",fdata)
        ret = ret_cur.fetchall()
        if len(ret) == 0:
            conn.execute("insert into trans values(?,?,?)",ldata)
            conn.commit()
            return 1
        ret_val = ret[0][0]
        if val > ret_val or ret_val == "NULL":
            conn.execute("update trans set server_m_time = ? where file_id = ?",data)
            conn.commit()
            return 1
        
        return 0

def get_data(conn, fileid, comm):
    ''' retrieve data from trans table based on command '''

    if conn is None:
        conn = open_db() 
    fid = (fileid,)
    cur = conn.execute("select * from trans where file_id=?",fid)
    data = cur.fetchall()
    print data
    if comm is 'CLIENT_M_TIME' or comm is 'client_m_time':
        return str(data[0][2])
    if comm is 'SERVER_M_TIME' or comm is 'server_m_time':
        return str(data[0][1])
    if comm is 'TIMESTAMP' or comm is 'timestamp':
        return str(data[0][1]) + '<##>' + str(data[0][2])

def show_data(conn):
    cur = conn.execute("select * from trans;")
    for row in cur:
        print row