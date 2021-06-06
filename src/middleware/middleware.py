"""
Here are all the sockets.
There shall not be any sockets outside of this file.

There shall be one socket in one seperate thread (multithreading)
for every tcp connections
also one socket in a thread for the udp socket for broadcast
"""

import threading
import socket
import ipaddress
from time import sleep
usleep = lambda x: sleep(x/1000_000.0) # sleep for x microseconds

from lib.myQueue import Q

######################################### PARAMETER Constants
BROADCAST_PORT = 61424
BUFFER_SIZE = 1024 # bytes
MSGLEN = 10000 # bytes?   # maximum length of message over tcp
SUBNETMASK = "255.255.255.0"
BROADCAST_LISTENER_SLEEP = 10 # microseconds

IP_ADRESS_OF_THIS_PC = socket.gethostbyname(socket.gethostname())
net = ipaddress.IPv4Network(IP_ADRESS_OF_THIS_PC + '/' + SUBNETMASK, False)
BROADCAST_IP = net.broadcast_address.exploded


class Middleware():
    deliveryQueue = Q()
    _holdBackQueue = Q()
    ipAdresses = {} # {uuid: (ipadress, port)} (str , int)
    MY_UUID = '' # later changed in the init, it is here to define it as a class variable, so that it is accessable easyly 
    leaderUUID = ''


    def __init__(self,UUID, statemashine):
        Middleware.MY_UUID = UUID 
        self.statemashine =  statemashine
        self._broadcastHandler = BroadcastHandler()
        self._unicastHandler = UnicastHandler()
        self._tcpUnicastHandler = TCPUnicastHandler()
        self.subscribeUnicastListener(self._updateAdresses)
        self.subscribeUnicastListener(self._checkForVotingAnnouncement)




    @classmethod
    def addIpAdress(cls, uuid, addr):
        cls.ipAdresses[uuid] = addr

    def broadcastToAll(self, command:str, data:str=''):
        self._broadcastHandler.broadcast(command+':'+data)
    
    def sendMessageTo(self, uuid:str, command:str, data:str=''): # unicast
        ipAdress = Middleware.ipAdresses[uuid]
        self._unicastHandler.sendMessage(ipAdress, command+':'+data)
    
    def sendTcpMessageTo(self, uuid:str, command:str, data:str=''):
        addr = Middleware.ipAdresses[uuid]
        self._tcpUnicastHandler.sendMessage(addr, command+':'+data)

    def multicastReliable(self, command:str, data:str=''):
        message = command+':'+data
        for key, addr in Middleware.ipAdresses.items():
            if key != Middleware.MY_UUID:
                self._tcpUnicastHandler.sendMessage(addr, message)

    def multicastOrderedReliable(self, command:str, data:str=''):
        pass

    def sendIPAdressesto(self,uuid):
        command='updateIpAdresses'
        s=''
        for uuid, (addr,port) in Middleware.ipAdresses.items():
            s += uuid+','+str(addr)+','+str(port)+'#'
        self.sendMessageTo(uuid,command,s)

    def subscribeBroadcastListener(self, observer_func):
        """observer_func gets called every time there this programm recieves a broadcast message

        Args:
            observer_func ([type]): observer_function needs to have func(self, messengerUUID:str, command:str, data:str)
        """
        self._broadcastHandler.subscribeBroadcastListener(observer_func)
    def subscribeUnicastListener(self, observer_func):
        """observer_func gets called every time this programm recieves a Unicast message

        Args:
            observer_func ([type]): observer_function needs to have func(self, messengerUUID:str, command:str, data:str)
        """
        self._unicastHandler.subscribeUnicastListener(observer_func)
    
    def subscribeTCPUnicastListener(self, observer_func):
        """observer_func gets called every time this programm recieves a Unicast message
        Args:
            observer_func ([type]): observer_function needs to have observer_func(messengerUUID:str, clientsocket:socket.socket, command:str, data:str) 
        """
        self._tcpUnicastHandler.subscribeTCPUnicastListener(observer_func)
    def _updateAdresses(self, messengerUUID:str, command:str, data:str):
        """_updateAdresses recieves and decodes the IPAdresses List from the function 
        sendIPAdressesto(self,uuid)

        Args:
            command (str): if this argument NOT == 'updateIpAdresses' this function returns without doing anything
            message (str): list of uuid's and IPAdresses
        """
        if command == 'updateIpAdresses':
            removedLastHashtag = data[0:-1] # everything, but the last character
            for addr in removedLastHashtag.split('#'):
                addrlist = addr.split(',')
                self.addIpAdress(addrlist[0], (addrlist[1], int(addrlist[2])))
                #                 uuid           ipadress           port of the unicastListener

    def _checkForVotingAnnouncement(self, messengerUUID:str, command:str, data:str):
        if command == 'voting':
            # if same UUID
            if data == self.MY_UUID:
                # i'm Simon
                print('\nI am the new Simon')
                # reliably multicast my UUID to all players
                self.multicastReliable('leaderElected', self.MY_UUID)
                # set leaderUUID as my UUID
                Middleware.leaderUUID = data
                # set GameState to simon_startNewRound
                self.statemashine.switchStateTo('simon_startNewRound')
            # if smaller UUID
            elif data < self.MY_UUID:
                # send my UUID to neighbour
                command = 'voting'
                data = self.MY_UUID
                print('\nsend voting command with my UUID (' + self.MY_UUID + ') to lowerNeighbour')
                self.sendMessageTo(self.findLowerNeighbour(), command, data)
            # if greater UUID
            elif data > self.MY_UUID:
                # send received UUID to neighbour
                command = 'voting'
                print('\nsend voting command with recevied UUID (' + data + ') to lowerNeighbour')
                self.sendMessageTo(self.findLowerNeighbour(), command, data)
        elif command == 'leaderElected':
            print('new Leader got elected')
            Middleware.leaderUUID = data
            # set GameState to state_player_waitGameStart_f
            self.statemashine.switchStateTo('state_player_waitGameStart_f')

    # diese Funktion muss aufgerufen werden um ein neues Voting zu starten
    def initiateVoting(self):
        # send to lowerNeighbour: voting with my UUID
        command = 'voting'
        data = self.MY_UUID
        print('\nStarted new Voting!')
        print('\nsend voting command with my UUID (' + self.MY_UUID + ') to lowerNeighbour')
        self.sendMessageTo(self.findLowerNeighbour(), command, data)

    def findLowerNeighbour(self):
        ordered = sorted(self.ipAdresses.keys())
        ownIndex = ordered.index(self.MY_UUID)

        neighbourUUID = ordered[ownIndex - 1]
        print('Neighbour: ' + neighbourUUID)
        return neighbourUUID
        # send to next higher node we start a voting with my UUID

class UnicastHandler():
    _serverPort = 0 # later changed in the init, it is here to define it as a class variable, so that it is accessable easyly 

    def __init__(self):
        # Create a UDP socket
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # AF_INET means that this socket Internet Protocol v4 addresses
                                                            #SOCK_DGRAM means this is a UDP scoket
        self._server_socket.bind(('', 0)) # ('', 0) '' use the lokal IP adress and 0 select a random open port
        UnicastHandler._serverPort = self._server_socket.getsockname()[1] # returns the previously selected (random) port
        print("ServerPort = ",UnicastHandler._serverPort)
        self.incommingUnicastHistory = []
        self._listenerList = [] # observer pattern

        # Create Thread to listen to UDP unicast
        self._listen_UDP_Unicast_Thread = threading.Thread(target=self._listenUnicast)
        self._listen_UDP_Unicast_Thread.start()

    
    def sendMessage(self, addr, message:str):
        self._server_socket.sendto(str.encode(Middleware.MY_UUID + '_'+IP_ADRESS_OF_THIS_PC + '_'+str(UnicastHandler._serverPort)+'_'+message), addr)
        print('UnicastHandler: sent message: ', message,"\n\tto: ", addr)

    def _listenUnicast(self):
        print("listenUDP Unicast Thread has started and not blocked Progress (by running in the background)")
        while True:
            print('\nUnicastHandler: Waiting to receive unicast message...\n')
            # Receive message from client
            # Code waits here until it recieves a unicast to its port
            # thats why this code needs to run in a different thread
            data, address = self._server_socket.recvfrom(BUFFER_SIZE) 
            data = data.decode('utf-8')
            print('UnicastHandler: Received message from client: ', address)
            print('\t\tMessage: ', data)

            if data:
                data=data.split('_')
                messengerUUID = data[0]
                messengerIP = data[1]
                messengerPort = int(data[2])    # this should be the port where the unicast listener socket 
                                                #(of the sender of this message) is listening on
                assert address ==  (messengerIP, messengerPort)                              
                message=data[3]
                messageSplit= message.split(':')
                assert len(messageSplit) == 2, "There should not be a ':' in the message"
                messageCommand = messageSplit[0]
                messageData = messageSplit[1]

                self.incommingUnicastHistory.append((message, address))
                for observer_func in self._listenerList:
                    observer_func(messengerUUID, messageCommand, messageData) 
               
    def subscribeUnicastListener(self, observer_func):
        self._listenerList.append(observer_func)

class TCPUnicastHandler():
    # this class needs to be initiated after the unicast Handler
    def __init__(self):
        # Create a TCP socket for listening
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # AF_INET means that this socket Internet Protocol v4 addresses
                                                            #SOCK_STREAM means this is a TCP scoket
        self._server_socket.bind(('', UnicastHandler._serverPort)) # ('', ) '' use the lokal IP adress and 0 select the same port as the udpUnicastHandler. you can use both protocols on the same port

        self.incommingUnicastHistory = []
        self._listenerList = [] # observer pattern

        # Create Thread to listen to TCP unicast
        self._listen_UDP_Unicast_Thread = threading.Thread(target=self._listenTCPUnicast)
        self._listen_UDP_Unicast_Thread.start()

    
    def sendMessage(self, addr: tuple, message:str): # open new connection; send message and close immediately
        self.sendSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # AF_INET means that this socket Internet Protocol v4 addresses
        self.sendSocket.bind(('', 0))

        print('\n\naddr for connect:   ', addr)
        try:
            self.sendSocket.connect(addr)
            messageBytes = str.encode(Middleware.MY_UUID + '_'+IP_ADRESS_OF_THIS_PC + '_'+str(UnicastHandler._serverPort)+'_'+message)
            self.sendSocket.send(messageBytes)
            print('TCPUnicastHandler: sent message: ', message,"\n\tto: ", addr)
        except ConnectionRefusedError:
            print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!  ERROR')
            print('Process on address ', addr, 'is not responding')
        finally:
            self.sendSocket.close() # Further sends are disallowed
        
        
        # ##### send data in chunks
        # totalsent = 0
        # while totalsent < MSGLEN:
        #     sent = self.sendSocket.send(messageBytes[totalsent:])
        #     if sent == 0:
        #         raise RuntimeError("socket connection broken")
        #     totalsent = totalsent + sent
        # ##### send data in chunks

    def _listenTCPUnicast(self):
        print("listenTCP Unicast Thread has started and not blocked Progress (by running in the background)")
        self._server_socket.listen(5) # The argument to listen tells the socket library that we want it to queue up as many as 5 connect requests (the normal max) before refusing outside connections. 
            #https://docs.python.org/3/howto/sockets.html
        # https://github.com/TejasTidke/Socket-Programming-TCP-Multithreading/blob/master/server/multiserver.py
        while True:
            print('\TCPUnicastHandler: Waiting for connection...\n')
            clientsocket, address = self._server_socket.accept()
            clientsocket.settimeout(60)
            # star a new thread, that is responsible for one new request from one peer.
            # in this thread, they can exchange more messages
            threading.Thread(target = self._listenToClient, args = (clientsocket,address)).start()


    def _listenToClient(self, clientsocket:socket.socket, address):
        print('Got tcp connection from: ', address)
        data = clientsocket.recv(BUFFER_SIZE)
        ################# recieve data in chunks
        # chunks = []
        # bytes_recd = 0
        # while bytes_recd < MSGLEN:
        #     chunk = clientsocket.recv(min(MSGLEN - bytes_recd, BUFFER_SIZE))
        #     if chunk == b'':
        #         raise RuntimeError("socket connection broken")
        #     chunks.append(chunk)
        #     bytes_recd = bytes_recd + len(chunk)
        # data = b''.join(chunks)
        ################# recieve data in chunks
        data = data.decode('utf-8')

        if data:
            data=data.split('_')
            messengerUUID = data[0]
            messengerIP = data[1]
            messengerPort = int(data[2])    # this should be the port where the unicast listener socket 
                                            #(of the sender of this message) is listening on
            #assert address ==  (messengerIP, messengerPort)                              
            message=data[3]
            messageSplit= message.split(':')
            assert len(messageSplit) == 2, "There should not be a ':' in the message"
            messageCommand = messageSplit[0]
            messageData = messageSplit[1]
            print("TCP Message recieved;\nmessageCommand \t :",messageCommand, "\messageData    \t :",messageData )
            self.incommingUnicastHistory.append((message, address))
            for observer_func in self._listenerList:
                observer_func(messengerUUID, clientsocket, messageCommand, messageData)
        # after the dedicated function has returned (, or no function wanted to deal with this request)
        # the socket can be closed
        clientsocket.close()

    def subscribeTCPUnicastListener(self, observer_func):
        self._listenerList.append(observer_func)

class BroadcastHandler():
    def __init__(self):
        self.incommingBroadcastQ = Q()
        self.incommingBroadcastHistory = []
        self._listenerList = []

        self._broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Create a UDP socket for Listening
        self._listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Set the socket to broadcast and enable reusing addresses
        self._listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind socket to address and port
        self._listen_socket.bind((IP_ADRESS_OF_THIS_PC, BROADCAST_PORT))

        # Create Thread to listen to UDP Broadcast
        self._listen_UDP_Broadcast_Thread = threading.Thread(target=self._listenUdpBroadcast)
        self._listen_UDP_Broadcast_Thread.start()

    def broadcast(self, broadcast_message:str):
        """Send message to the broadcast Port defined at lauch of the Programm

        Args:
            broadcast_message (str): needs to have the format  "command:data" (the data could be csv encode with , and #)
        """
        # Send message on broadcast address
        self._broadcast_socket.sendto(str.encode(Middleware.MY_UUID + '_'+IP_ADRESS_OF_THIS_PC + '_'+str(UnicastHandler._serverPort)+'_'+broadcast_message, encoding='utf-8'), (BROADCAST_IP, BROADCAST_PORT))
        #                                                                                                                  ^this is the port where the _listen_UDP_Unicast_Thread ist listening on
        #self.broadcast_socket.close()

    def subscribeBroadcastListener(self, observer_func):
        self._listenerList.append(observer_func)
    def _listenUdpBroadcast(self):
        print("listenUDP Broadcast Thread has started and not blocked Progress (by running in the background)")
        while True:
            # Code waits here until it recieves a unicast to its port
            # thats why this code needs to run in a different thread
            data, addr = self._listen_socket.recvfrom(BUFFER_SIZE)
            data = data.decode('utf-8')
            if data:
                data=data.split('_')
                messengerUUID = data[0]
                messengerIP = data[1]
                messengerPort = int(data[2])    # this should be the port where the unicast listener socket 
                                                #(of the sender of this message) is listening on
                message=data[3]
                Middleware.addIpAdress(messengerUUID,(messengerIP, messengerPort)) # add this to list override if already present
                if messengerUUID != Middleware.MY_UUID:
                    print("Received broadcast message form",addr, ": ", message)
                    message=data[3]
                    messageSplit= message.split(':')
                    assert len(messageSplit) == 2, "There should not be a ':' in the message"
                    messageCommand = messageSplit[0]
                    messageData = messageSplit[1]
                    self.incommingBroadcastHistory.append((messengerUUID, message))
                    for observer_func in self._listenerList:
                        observer_func(messengerUUID, messageCommand, messageData)
                data = None

class ReliableMulticastHandler():
    pass
