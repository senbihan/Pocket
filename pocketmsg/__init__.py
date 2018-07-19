import os
import librsync as sync
from dboperations import *
import tempfile

MAX_FILE_LEN = 50
MAX_SPOOL = 1024 ** 2 * 5

class SharedPort:
    client_port = 52132
    server_port = 57929
    client_sync_port = 25796

    client_port_used = False
    server_port_used = False
    client_sync_port_used = False

class msgCode:
    CREQ    = '0001'
    SENDSIG = '0002'
    SENDDEL = '0003'
    REQSIG  = '0004'
    REQSMT  = '0005'
    SENDSMT = '0006'
    SENDNOC = '0007'
    REQTOT  = '0008'
    SENDDAT = '0009'
    SERVSYNC = '0010'
    CONFLICT = '0011'
    SENDCMT = '0012'
    SREQ = '0013'
    TERMIN = '0050'

    delim = '|#|'
    endmark = '||<@@>||'

def get_creq_msg(clientid, filename, conn = None):
    ''' create creq msg '''
    
    if conn is None:
        conn = open_db()
    data = get_data(conn,filename,"TIMESTAMP")
    msg = msgCode.CREQ + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data + msgCode.endmark
    #print "creq msg", msg
    return msg

def get_sensig_msg(clientid, filename, conn = None):
    ''' create sendsig msg '''    

    if conn is None:
        conn = open_db()
    sig = sync.signature(open(filename,"rb+"))
    data = sig.read()
    msg = msgCode.SENDSIG + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + str(data) + msgCode.endmark
    #print "sendsig msg", msg
    return msg

def get_senddel_msg(clientid, filename, data, conn = None):
    ''' create senddel msg 
        filename : source filename
    '''
    
    if conn is None:
        conn = open_db()
    signature = tempfile.SpooledTemporaryFile(max_size=MAX_SPOOL, mode='wb+')
    signature.write(data)
    signature.seek(0)
    src = open(filename, 'rb')
    delta = sync.delta(src,signature)
    sdata = delta.read()
    msg = msgCode.SENDDEL + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + str(sdata) + msgCode.endmark
    #print "senddel msg", msg
    return msg 

def get_reqsig_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    msg = msgCode.REQSIG + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + '\0' + msgCode.endmark
    return msg


def get_reqtot_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    msg = msgCode.REQTOT + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + '\0' + msgCode.endmark
    return msg

def get_senddat_header(clientid, filename, conn = None):
    
    if conn is None:
        conn = open_db()
    
    header = msgCode.SENDDAT + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim 
    return header

def get_sendsmt_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    
    data = get_data(conn,filename,"server_m_time")
    msg = msgCode.SENDSMT + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data + msgCode.endmark
    return msg


def get_sendcmt_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    
    data = get_data(conn,filename,"client_m_time")
    msg = msgCode.SENDCMT + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data + msgCode.endmark
    return msg

def get_conflict_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    
    data = '\0'
    msg = msgCode.CONFLICT + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data + msgCode.endmark
    return msg


def get_servsync_msg(clientid, filename, conn = None):

    # filename is insignificant here 
    if conn is None:
        conn = open_db()
    data = '\0'
    msg = msgCode.SERVSYNC + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data + msgCode.endmark
    return msg

def get_sendnoc_msg(clientid, filename, conn = None):
    
    if conn is None:
        conn = open_db()
    data = '\0'
    msg = msgCode.SENDNOC + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data + msgCode.endmark
    return msg


def get_sreq_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    data = get_data(conn,filename,"TIMESTAMP")
    msg = msgCode.SREQ + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data + msgCode.endmark
    return msg

def get_terminate_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    data = '\0'
    msg = msgCode.TERMIN + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data + msgCode.endmark
    return msg