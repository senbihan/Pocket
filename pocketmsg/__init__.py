import os
import librsync as sync
from dboperations import *
import tempfile

MAX_FILE_LEN = 50
MAX_SPOOL = 1024 ** 2 * 5

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
    msg = msgCode.REQDEL + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + '\0' + msgCode.endmark
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

def get_servsync_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    data = '\0'
    msg = msgCode.SERVSYNC + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data + msgCode.endmark
    return msg