#!/usr/bin/python3
import sys
if sys.path[0].endswith("worker"):
    sys.path[0] = sys.path[0][:-6]
from utils import env, tools
config = env.getenv("CONFIG")
#config = "/opt/docklet/local/docklet-running.conf"
tools.loadenv(config)
from utils.log import initlogging
initlogging("docklet-taskcontroller")
from utils.log import logger

from concurrent import futures
import grpc
#from utils.log import logger
#from utils import env
import json,lxc,subprocess,threading,os,time,traceback
from utils import imagemgr
from protos import rpc_pb2, rpc_pb2_grpc

def ip_to_int(addr):
    [a, b, c, d] = addr.split('.')
    return (int(a)<<24) + (int(b)<<16) + (int(c)<<8) + int(d)

def int_to_ip(num):
    return str((num>>24)&255)+"."+str((num>>16)&255)+"."+str((num>>8)&255)+"."+str(num&255)

class TaskController(rpc_pb2_grpc.WorkerServicer):

    def __init__(self):
        rpc_pb2_grpc.WorkerServicer.__init__(self)
        self.imgmgr = imagemgr.ImageMgr()
        self.fspath = env.getenv('FS_PREFIX')
        self.confpath = env.getenv('DOCKLET_CONF')
        self.lock = threading.Lock()
        self.cons_gateway = env.getenv('BATCH_GATEWAY')
        self.cons_ips = env.getenv('BATCH_NET')
        logger.info("Batch gateway ip address %s" % self.cons_gateway)
        logger.info("Batch ip pools %s" % self.cons_ips)

        self.cidr = 32 - int(self.cons_ips.split('/')[1])
        self.ipbase = ip_to_int(self.cons_ips.split('/')[0])
        self.free_ips = []
        for i in range(2, (1 << self.cidr) - 1):
            self.free_ips.append(i)
        logger.info("Free ip addresses pool %s" % str(self.free_ips))

        logger.info('TaskController init success')

    # Need Locks
    def acquire_ip(self):
        self.lock.acquire()
        if len(self.free_ips) == 0:
            return [False, "No free ips"]
        ip = int_to_ip(self.ipbase + self.free_ips[0])
        self.free_ips.remove(self.free_ips[0])
        logger.info(str(self.free_ips))
        self.lock.release()
        return [True, ip + "/" + str(32 - self.cidr)]

    # Need Locks
    def release_ip(self,ipstr):
        self.lock.acquire()
        ipnum = ip_to_int(ipstr.split('/')[0]) - self.ipbase
        self.free_ips.append(ipnum)
        logger.info(str(self.free_ips))
        self.lock.release()

    def process_task(self, request, context):
        logger.info('excute task with parameter: ' + str(request))
        taskid = request.id
        instanceid = request.instanceid

        # get config from request
        command = request.parameters.command.commandLine #'/root/getenv.sh'  #parameter['Parameters']['Command']['CommandLine']
        #envs = {'MYENV1':'MYVAL1', 'MYENV2':'MYVAL2'} #parameters['Parameters']['Command']['EnvVars']
        pkgpath = request.parameters.command.packagePath
        envs = request.parameters.command.envVars
        envs['taskid'] = str(taskid)
        envs['instanceid'] = str(instanceid)
        image = {}
        image['name'] = request.cluster.image.name
        if request.cluster.image.type == rpc_pb2.Image.PRIVATE:
            image['type'] = 'private'
        elif request.cluster.image.type == rpc_pb2.Image.PUBLIC:
            image['type'] = 'public'
        else:
            image['type'] = 'base'
        image['owner'] = request.cluster.image.owner
        username = request.username
        lxcname = '%s-batch-%s-%s' % (username,taskid,str(instanceid))
        instance_type =  request.cluster.instance

        # acquire ip
        [status, ip] = self.acquire_ip()
        if not status:
            return rpc_pb2.Reply(status=rpc_pb2.Reply.REFUSED, message=ip)

        # prepare image and filesystem
        status = self.imgmgr.prepareFS(username,image,lxcname,str(instance_type.disk))
        if not status:
            self.release_ip(ip)
            return rpc_pb2.Reply(status=rpc_pb2.Reply.REFUSED, message="Create container for batch failed when preparing filesystem")

        rootfs = "/var/lib/lxc/%s/rootfs" % lxcname

        if not os.path.isdir("%s/global/users/%s" % (self.fspath,username)):
            path = env.getenv('DOCKLET_LIB')
            subprocess.call([path+"/userinit.sh", username])
            logger.info("user %s directory not found, create it" % username)
            sys_run("mkdir -p /var/lib/lxc/%s" % lxcname)
            logger.info("generate config file for %s" % lxcname)

        def config_prepare(content):
            content = content.replace("%ROOTFS%",rootfs)
            content = content.replace("%HOSTNAME%","batch-%s" % instanceid)
            content = content.replace("%CONTAINER_MEMORY%",str(instance_type.memory))
            content = content.replace("%CONTAINER_CPU%",str(instance_type.cpu*100000))
            content = content.replace("%FS_PREFIX%",self.fspath)
            content = content.replace("%LXCSCRIPT%",env.getenv("LXC_SCRIPT"))
            content = content.replace("%USERNAME%",username)
            content = content.replace("%LXCNAME%",lxcname)
            content = content.replace("%IP%",ip)
            content = content.replace("%GATEWAY%",self.cons_gateway)
            return content

        logger.info(self.confpath)
        conffile = open(self.confpath+"/container.batch.conf", 'r')
        conftext = conffile.read()
        conffile.close()

        conftext = config_prepare(conftext)

        conffile = open("/var/lib/lxc/%s/config" % lxcname, 'w')
        conffile.write(conftext)
        conffile.close()

        container = lxc.Container(lxcname)
        if not container.start():
            logger.error('start container %s failed' % lxcname)
            self.release_ip(ip)
            return rpc_pb2.Reply(status=rpc_pb2.Reply.REFUSED,message="Can't start the container")
        else:
            logger.info('start container %s success' % lxcname)

        #mount oss here

        thread = threading.Thread(target = self.excute_task, args=(taskid,instanceid,envs,lxcname,pkgpath,command,ip))
        thread.setDaemon(True)
        thread.start()

        return rpc_pb2.Reply(status=rpc_pb2.Reply.ACCEPTED,message="")

    def excute_task(self,taskid,instanceid,envs,lxcname,pkgpath,command,ip):
        lxcfspath = "/var/lib/lxc/"+lxcname+"/rootfs"
        scriptname = "batch_job.sh"
        try:
            scriptfile = open(lxcfspath+"/root/"+scriptname,"w")
            scriptfile.write("#!/bin/bash\n")
            scriptfile.write("cd "+str(pkgpath)+"\n")
            scriptfile.write(command)
            scriptfile.close()
        except Exception as err:
            logger.error(traceback.format_exc())
            logger.error("Fail to write script file with taskid(%s) instanceid(%s)" % (str(taskid),str(instanceid)))
        else:
            cmd = "lxc-attach -n " + lxcname
            for envkey,envval in envs.items():
                cmd = cmd + " -v %s=%s" % (envkey,envval)
            cmd = cmd + " -- /bin/bash \"" + "/root/" + scriptname + "\""
            logger.info('run task with command - %s' % cmd)
            ret = subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT, shell=True)
            logger.info(ret)
            if ret.returncode == 0:
                #call master rpc function to tell the taskmgr
                pass
            else:
                #call master rpc function to tell the wrong
                pass

        #umount oss here

        container = lxc.Container(lxcname)
        if container.stop():
            logger.info("stop container %s success" % lxcname)
        else:
            logger.error("stop container %s failed" % lxcname)

        logger.info("deleting container:%s" % lxcname)
        if self.imgmgr.deleteFS(lxcname):
            logger.info("delete container %s success" % lxcname)
        else:
            logger.error("delete container %s failed" % lxcname)

        logger.info("release ip address %s" % ip)
        self.release_ip(ip)


_ONE_DAY_IN_SECONDS = 60 * 60 * 24

def TaskControllerServe():
    max_threads = int(env.getenv('BATCH_MAX_THREAD_WORKER'))
    worker_port = int(env.getenv('BATCH_WORKER_PORT'))
    logger.info("Max Threads on a worker is %d" % max_threads)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_threads))
    rpc_pb2_grpc.add_WorkerServicer_to_server(TaskController(), server)
    server.add_insecure_port('[::]:'+str(worker_port))
    server.start()
    logger.info("Start TaskController Servicer on port:%d" % worker_port)
    try:
        while True:
            time.sleep(_ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    TaskControllerServe()
