import sys
if sys.path[0].endswith("master"):
    sys.path[0] = sys.path[0][:-6]

import grpc,time

from protos import rpc_pb2, rpc_pb2_grpc
import random, string

def run():
    channel = grpc.insecure_channel('localhost:50051')
    stub = rpc_pb2_grpc.WorkerStub(channel)

    #comm = rpc_pb2.Command(commandLine="ls /root;sleep 5;ls /root", packagePath="/root", envVars={'test1':'10','test2':'20'}) # | awk '{print \"test\\\"\\n\"}'
    #paras = rpc_pb2.Parameters(command=comm, stderrRedirectPath="/root/nfs/batch_{jobid}/", stdoutRedirectPath="/root/nfs/batch_{jobid}/")

    img = rpc_pb2.Image(name="base", type=rpc_pb2.Image.BASE, owner="docklet")
    inst = rpc_pb2.Instance(cpu=1, memory=1000, disk=1000, gpu=0)
    mnt = rpc_pb2.Mount(localPath="",provider='aliyun',remotePath="test-for-docklet",other="oss-cn-beijing.aliyuncs.com",accessKey="LTAIdl7gmmIhfqA9",secretKey="")
    network = rpc_pb2.Network(ipaddr="10.0.4.2/24",gateway="10.0.4.1",masterip="192.168.0.1",brname="batch-root-test")
    vnode = rpc_pb2.VNode(image=img, instance=inst, mount=[],network=network)
    vnodeinfo = rpc_pb2.VNodeInfo(taskid="test",username="root",vnodeid=1,vnode=vnode)

    #task = rpc_pb2.TaskInfo(id="test",username="root",instanceid=1,instanceCount=1,maxRetryCount=1,parameters=paras,cluster=clu,timeout=60000,token=''.join(random.sample(string.ascii_letters + string.digits, 8)))

    response = stub.start_vnode(vnodeinfo)
    print("Batch client received: " + str(response.status)+" "+response.message)

def stop_task():
    channel = grpc.insecure_channel('localhost:50051')
    stub = rpc_pb2_grpc.WorkerStub(channel)

    taskmsg = rpc_pb2.TaskMsg(taskid="test",username="root",instanceid=1,instanceStatus=rpc_pb2.COMPLETED,token="test",errmsg="")
    reportmsg = rpc_pb2.ReportMsg(taskmsgs = [taskmsg])

    response = stub.stop_tasks(reportmsg)
    print("Batch client received: " + str(response.status)+" "+response.message)

def stop_vnode():
    channel = grpc.insecure_channel('localhost:50051')
    stub = rpc_pb2_grpc.WorkerStub(channel)
    network = rpc_pb2.Network(brname="batch-root-test")
    vnodeinfo = rpc_pb2.VNodeInfo(taskid="test",username="root",vnodeid=1,vnode=rpc_pb2.VNode(network=network))

    response = stub.stop_vnode(vnodeinfo)
    print("Batch client received: " + str(response.status)+" "+response.message)

def start_task():
    channel = grpc.insecure_channel('localhost:50051')
    stub = rpc_pb2_grpc.WorkerStub(channel)

    comm = rpc_pb2.Command(commandLine="ls /root;sleep 5;ls /root", packagePath="/root", envVars={'test1':'10','test2':'20'}) # | awk '{print \"test\\\"\\n\"}'
    paras = rpc_pb2.Parameters(command=comm, stderrRedirectPath="/root/nfs/batch_{jobid}/", stdoutRedirectPath="/root/nfs/batch_{jobid}/")
    taskinfo = rpc_pb2.TaskInfo(taskid="test",username="root",vnodeid=1,parameters=paras,timeout=20,token="test")

    response = stub.start_task(taskinfo)
    print("Batch client received: " + str(response.status)+" "+response.message)


if __name__ == '__main__':
    #for i in range(10):
    run()
    #start_task()
    #stop_vnode()
    #time.sleep(4)
    #stop_task()
