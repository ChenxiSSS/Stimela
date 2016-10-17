import subprocess
import os
import sys
from cStringIO import StringIO as io
from stimela import utils
import json
from utils import stimela_logger
import stimela
import time
import datetime
import tempfile

class DockerError(Exception):
    pass


def build(image, build_path, tag=None, build_args=None):
    """ build a docker image"""

    if tag:
        image = ":".join([image, tag])

    if build_args:
        stdw = tempfile.NamedTemporaryFile(dir=build_path)
        with open("%s/Dockerfile"%build_path) as std:
            dfile = std.readlines()

        for line in dfile:
            if line.lower().startswith("cmd"):
                for arg in build_args:
                    stdw.write(arg+"\n")
                stdw.write(line)
            else:
                stdw.write(line)
        stdw.flush()
        utils.xrun("docker build", ["--force-rm","-f", stdw.name, 
                    "-t", image, 
                    build_path])

        stdw.close()
    else:
        utils.xrun("docker build", ["-t", image, 
                    build_path])

def pull(image, tag=None):
    """ pull a docker image """
    if tag:
        image = ":".join([image, tag])

    utils.xrun("docker pull", [image])


def seconds_hms(seconds):
    return str(datetime.timedelta(seconds=seconds))


class Container(object):
    def __init__(self, image, name, 
                 volumes=None, environs=None,
                 label="", logger=None, 
                 shared_memory="1gb",
                 log_container=True):
        """
        Python wrapper to docker engine tools for managing containers.
        """
    
        self.image = image
        self.name = name
        self.label = label
        self.volumes = volumes or []
        self.environs = environs or []
        self.logger = logger
        self.status = None
        self.WORKDIR = None
        self.COMMAND = None
        self.shared_memory = shared_memory
        self.PID = os.getpid()
        self.uptime = "00:00:00"

        if log_container:
            self.log_container = stimela_logger.Container(stimela.LOG_CONTAINERS)


    def  add_volume(self, host, container, perm="rw"):

        if os.path.exists(host):
            if self.logger:
                self.logger.debug("Mounting volume [%s] in container [%s] at [%s]"%(host, self.name, container))
            host = os.path.abspath(host)
        else:
            raise IOError("Directory [%s] cannot be mounted on container: File doesn't exist"%host)
        
        self.volumes.append(":".join([host,container,perm]))


    def add_environ(self, key, value):
        if self.logger:
            self.logger.debug("Adding environ varaible [%s=%s] in container [%s]"%(key, value, self.name))
        self.environs.append("=".join([key, value]))


    def create(self, *args):

        if self.volumes: 
            volumes = " -v " + " -v ".join(self.volumes)
        else:
            volumes = ""
        if self.environs:
            environs = environs = " -e "+" -e ".join(self.environs)
        else:
            environs = ""

        
        self._print("Instantiating container [%s]. The container ID is printed bellow."%self.name)
        utils.xrun("docker create", list(args) + [volumes, environs,
                        "-w %s"%(self.WORKDIR) if self.WORKDIR else "",
                        "--name", self.name, "--shm-size", self.shared_memory,
                        self.image,
                        self.COMMAND or ""])

        self.log_container.add(self.info(), self.PID)
        self.status = "created"

    def info(self):

        output = subprocess.check_output("docker inspect %s"%(self.name), shell=True)
        output_file = io(output[3:-3])
        jdict = json.load(output_file)
        output_file.close()

        return jdict
    
    
    def get_log(self):
        output = subprocess.check_output("docker logs %s"%(self.name), shell=True)
        return output

        
    def start(self):
        running = True
        tstart = time.time()
        utils.xrun("docker start -a", [self.name])
        self.status = "running"
        self.log_container.update(self.info(), uptime="00:00:00")

        while running:
            time.sleep(1)
            uptime = seconds_hms(time.time() - tstart)
            self.log_container.update(self.info(), uptime=uptime)
            self.uptime = uptime

            status = self.info()["State"]["Status"]
            if status != "running":
                running = False

            #with open(self.logfile, "w") as stdw:
            #    stdw.write(self.get_log())

        self._print("Container [%s] has executed successfully."%(self.name))
        uptime = seconds_hms(time.time() - tstart)
        self.uptime = uptime
        self.log_container.update(self.info(), uptime=uptime)
        
        self.container_logger = self.get_log()
        self.status = "exited"

    
    def stop(self):
        dinfo = self.info()
        status = dinfo["State"]["Status"]
        if status == "running":
            utils.xrun("docker stop", [self.name])

        self._print("Container [self.name] has been")
        self.log_container.update(self.info(), self.uptime)


    def remove(self):
        dinfo = self.info()
        status = dinfo["State"]["Status"]
        if status != "running":
            utils.xrun("docker rm", [self.name])
        else:
            raise DockerError("Container [%s] has not been stopped, cannot remove"%(self.name))

        self.log_container.rm(self.name)

    def _print(self, message):
        if self.logger:
            self.logger.info(message)
        else:
            print(message)





