import os
import librsync as sync
from dboperations import *

MAX_FILE_LEN = 50

class msgCode:
    CREQ    = '0001'
    SENDSIG = '0002'
    SENDDEL = '0003'
    REQDEL  = '0004'
    REQSMT  = '0005'
    SENDSMT = '0006'
    SENDNOC = '0007'
    REQTOT  = '0008'
    delim = '|#|'


def get_creq_msg(clientid, filename, conn = None):
    ''' create creq msg '''
    
    if conn is None:
        conn = open_db()
    data = get_data(conn,filename,"TIMESTAMP")
    msg = msgCode.CREQ + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data
    print "creq msg", msg
    return msg

def get_sensig_msg(clientid, filename, conn = None):
    ''' create sendsig msg '''    

    if conn is None:
        conn = open_db()
    sig = sync.signature(file(filename,"rb+"))
    data = sig.read()
    msg = msgCode.SENDSIG + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data
    print "sendsig msg", msg
    return msg

def get_senddel_msg(clientid, filename, signature, conn = None):
    ''' create senddel msg 
        filename : source filename
    '''
    
    if conn is None:
        conn = open_db()
    delta = sync.delta(file(filename),signature)
    data = delta.read()
    msg = msgCode.SENDDEL + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + data
    print "senddel msg", msg
    return msg 

def get_reqdel_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    msg = msgCode.REQDEL + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + '\0'
    return msg


def get_reqtot_msg(clientid, filename, conn = None):

    if conn is None:
        conn = open_db()
    msg = msgCode.REQTOT + msgCode.delim + clientid + msgCode.delim + filename + msgCode.delim + '\0'
    return msg
