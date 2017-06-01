import xmlrpclib
import time
import random
RPC_SERVER_PORT = 16264
cnt = 0
node1 = xmlrpclib.ServerProxy('http://172.17.0.2:%s' % RPC_SERVER_PORT)
node2 = xmlrpclib.ServerProxy('http://172.17.0.3:%s' % RPC_SERVER_PORT)
node3 = xmlrpclib.ServerProxy('http://172.17.0.4:%s' % RPC_SERVER_PORT)

proxy = [node1, node2, node3]

def generate_name_set():
    name_list = []
    for i in range(0, 1000):
        name_list.append('bar' + str(i))
    return name_list

start_time = time.time()
namelist = generate_name_set()

# do register name
for name in namelist:
    node_index = random.randint(0, 2)
    assert node_index in [0, 1, 2]
    proxy_node = proxy[node_index]
    res = proxy_node.rpc_register_name(name)
    print res
# flush
node2.rpc_register_name('flush')
end_time = time.time()
print "time is %s" % str(end_time - start_time)
time.sleep(2)

# do count successful name register
for name in namelist:
    result = node2.rpc_get_name(name)
    print result
    if result is not None:
        cnt += 1

print '*********************cnt = %s ********************' % cnt

