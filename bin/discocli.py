#!/usr/bin/env python

import os, sys
import fileinput

from clx import OptionParser, Program
from clx.server import Server

class DiscoOptionParser(OptionParser):
    def __init__(self, **kwargs):
        OptionParser.__init__(self, **kwargs)
        self.add_option('-k', '--sort-stats',
                        action='append',
                        default=[],
                        help='keys to use for sorting profiling statistics')
        self.add_option('-S', '--status',
                        action='store_true',
                        help='show job status when printing jobs')

class Disco(Program):
    def default(self, program, *args):
        if args:
            raise Exception("unrecognized command: %s" % ' '.join(args))
        print "Disco master located at %s" % self.settings['DISCO_MASTER']

    def main(self):
        self.settings.ensuredirs()
        super(Disco, self).main()

    @property
    def disco(self):
        from disco.core import Disco
        return Disco(self.settings['DISCO_MASTER'])

    @property
    def master(self):
        return Master(self.settings)

    @property
    def settings_class(self):
        from disco.settings import DiscoSettings
        return DiscoSettings

    @property
    def tests(self):
        for name in os.listdir(self.tests_path):
            if name.startswith('test_'):
                test, ext = os.path.splitext(name)
                if ext == '.py':
                    yield test

    @property
    def tests_path(self):
        return os.path.join(self.settings['DISCO_HOME'], 'tests')

class Master(Server):
    def __init__(self, settings):
        super(Master, self).__init__(settings)
        self.setid()

    @property
    def args(self):
        return self.basic_args + ['-detached',
                                  '-heart',
                                  '-kernel', 'error_logger', '{file, "%s"}' % self.log_file]
    @property
    def basic_args(self):
        settings = self.settings
        ebin = lambda d: os.path.join(settings['DISCO_MASTER_HOME'], 'ebin', d)
        return settings['DISCO_ERLANG'].split() + \
               ['+K', 'true',
                '-rsh', 'ssh',
                '-connect_all', 'false',
                '-sname', self.name,
                '-pa', ebin(''),
                '-pa', ebin('mochiweb'),
                '-pa', ebin('ddfs'),
                '-eval', 'application:start(disco)']

    @property
    def host(self):
        from socket import gethostname
        return gethostname()

    @property
    def port(self):
        return self.settings['DISCO_PORT']

    @property
    def log_dir(self):
        return self.settings['DISCO_LOG_DIR']

    @property
    def pid_dir(self):
        return self.settings['DISCO_PID_DIR']

    @property
    def env(self):
        env = self.settings.env
        env.update({'DISCO_MASTER_PID': self.pid_file})
        return env

    @property
    def name(self):
        return '%s_master' % self.settings['DISCO_NAME']

    @property
    def nodename(self):
        return '%s@%s' % (self.name, self.host.split('.', 1)[0])

    def nodaemon(self):
        return ('' for x in self.start(*self.basic_args))

    def setid(self):
        user = self.settings['DISCO_USER']
        if user != os.getenv('LOGNAME'):
            if os.getuid() != 0:
                raise Exception("Only root can change DISCO_USER")
            try:
                import pwd
                uid, gid, x, home = pwd.getpwnam(user)[2:6]
                os.setgid(gid)
                os.setuid(uid)
                os.environ['HOME'] = home
            except Exception, x:
                raise Exception("Could not switch to the user '%s'" % user)

@Disco.command
def debug(program, host=''):
    """Usage: [host]

    Connect to master Erlang process via remote shell.
    Host is only necessary when master is running on a remote machine.
    """
    from subprocess import Popen
    master = program.master
    nodename = '%s@%s' % (master.name, host) if host else master.nodename
    args = program.settings['DISCO_ERLANG'].split() + \
           ['-remsh', nodename,
            '-sname', '%s_remsh' % os.getpid()]
    if Popen(args).wait():
        raise Exception("Could not connect to %s (%s)" % (host, nodename))
    print "closing remote shell to %s (%s)" % (host, nodename)

@Disco.command
def help(program, *args):
    """
    Print program or command help.
    """
    command, leftover = program.search(args)
    print command

@Disco.command
def nodaemon(program):
    """
    Start the master in the current process.
    Note: quitting the shell will stop the master.
    """
    for message in program.master.nodaemon():
        print message

@Disco.command
def restart(program):
    """
    Restart the master.
    """
    for message in program.master.restart():
        print message

@Disco.command
def start(program):
    """
    Start the master.
    """
    for message in program.master.start():
        print message

@Disco.command
def status(program):
    """
    Display running state of the master.
    """
    for message in program.master.status():
        print message

@Disco.command
def stop(program):
    """
    Stop the master.
    """
    for message in program.master.stop():
        print message

@Disco.command
def test(program, *tests):
    """Usage: [testname ...]

    Run the specified tests or the entire test suite if none are specified.
    """
    from disco.test import DiscoTestRunner
    if not tests:
        tests = list(program.tests)
    os.environ.update(program.settings.env)
    sys.path.insert(0, program.tests_path)
    DiscoTestRunner(program.settings).run(*tests)

@Disco.command
def config(program):
    """Usage:

    Print the disco master configuration.
    """
    for config in program.disco.config:
        print "\t".join(config)

@Disco.command
def deref(program, *files):
    """Usage: [file ...]

    Dereference the dir:// urls in file[s] or stdin and print them to stdout.
    """
    from disco.util import parse_dir
    for line in fileinput.input(files):
        for url in parse_dir(line.strip()):
            print url

@Disco.command
def jobdict(program, jobname):
    """Usage: jobname

    Print the jobdict for the named job.
    """
    print jobname
    for key, value in program.disco.jobdict(jobname).iteritems():
        print "\t%s\t%s" % (key, value)

@Disco.command
def jobs(program):
    """Usage: [-S]

    Print a list of disco jobs and optionally their statuses.
    """
    for offset, status, job in program.disco.joblist():
        print "%s\t%s" % (job, status) if program.options.status else job

@Disco.command
def kill(program, *jobnames):
    """Usage: jobname ...

    Kill the named jobs.
    """
    for jobname in jobnames:
        program.disco.kill(jobname)

@Disco.command
def mapresults(program, jobname):
    """Usage: jobname

    Print the list of results from the map phase of a job.
    This is useful for resuming a job which has failed during reduce.
    """
    for result in program.disco.mapresults(jobname):
        print result

@Disco.command
def oob(program, jobname):
    """Usage: jobname

    Print the oob keys for the named job.
    """
    from disco.core import Job
    for key in Job(program.disco, jobname).oob_list():
        print key

@oob.subcommand
def get(program, key, jobname):
    """Usage: key jobname

    Print the oob value for the given key and jobname.
    """
    from disco.core import Job
    print Job(program.disco, jobname).oob_get(key)

@Disco.command
def pstats(program, jobname):
    """Usage: jobname

    Print the profiling statistics for the named job.
    Assumes the job was run with profile flag enabled.
    """
    sort_stats = program.options.sort_stats or ['cumulative']
    program.disco.profile_stats(jobname).sort_stats(*sort_stats).print_stats()

@Disco.command
def purge(program, *jobnames):
    """Usage: jobname ...

    Purge the named jobs.
    """
    for jobname in jobnames:
        program.disco.purge(jobname)

@Disco.command
def results(program, jobname):
    """Usage: jobname

    Print the list of results for a completed job.
    """
    status, results = program.disco.results(jobname)
    for result in results:
           print result

if __name__ == '__main__':
    Disco(option_parser=DiscoOptionParser()).main()

    # Workaround for "disco test" in Python2.5 which doesn't shutdown the
    # test_server thread properly.
    sys.exit(0) # XXX still needed?
