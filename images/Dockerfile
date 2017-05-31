FROM ubuntu:14.04

RUN apt-get -y install python-pip
RUN apt-get -y install vim
RUN pip install protocoin
RUN pip install simplejson
RUN pip install -U pybitcoin
RUN apt-get install -y python-software-properties software-properties-common
RUN add-apt-repository ppa:bitcoin/bitcoin
RUN apt-get update
RUN apt-get install -y bitcoind

RUN mkdir -p /code/zonefile-manage
RUN git clone https://github.com/wutengcoding/zonefile-manage.git /code/zonefile-manage
WORKDIR /code/zonefile-manage
CMD python bin/zonefilemanage_server.py








