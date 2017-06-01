FROM ubuntu:14.04

RUN apt-get -y update && apt-get -y install python-setuptools python-dev git-core build-essential libssl-dev libffi-dev
RUN apt-get -y install python-pip
RUN apt-get -y install vim
RUN pip install protocoin
RUN pip install simplejson
RUN pip install -U pybitcoin
RUN apt-get -y update && apt-get install -y python-software-properties software-properties-common
RUN add-apt-repository ppa:bitcoin/bitcoin
RUN apt-get update
RUN apt-get install -y bitcoind
RUN pip install flask

RUN mkdir -p /code/zonefile-manage4
RUN git clone https://github.com/wutengcoding/cnnic_blockchain_zonefile.git /code/zonefile-manage4
WORKDIR /code/zonefile-manage4
CMD python bin/zonefilemanage_server.py







