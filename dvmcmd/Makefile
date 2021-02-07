CC      = gcc
CXX     = g++
CFLAGS  = -g -O3 -Wall -std=c++0x -pthread -I.
LIBS    = -lpthread
LDFLAGS = -g

OBJECTS = \
		network/UDPSocket.o \
		edac/SHA256.o \
		RemoteCommand.o

all:	dvmcmd

dvmcmd: $(OBJECTS) 
		$(CXX) $(OBJECTS) $(CFLAGS) $(LIBS) -o dvmcmd

%.o: %.cpp
		$(CXX) $(CFLAGS) -c -o $@ $<

clean:
		$(RM) dvmcmd *.o *.d *.bak *~ network/*.o edac/*.o
