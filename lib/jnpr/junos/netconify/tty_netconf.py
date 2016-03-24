import re
import time
from lxml import etree
from lxml.builder import E
import time

from jnpr.junos.netconify.fact import Fact

__all__ = ['xmlmode_netconf']

_NETCONF_EOM = ']]>]]>'
_xmlns = re.compile('xmlns=[^>]+')
_xmlns_strip = lambda text: _xmlns.sub('', text)
_junosns = re.compile('junos:')
_junosns_strip = lambda text: _junosns.sub('', text)

# =========================================================================
# xmlmode_netconf
# =========================================================================


class tty_netconf(object):

    """
    Basic Junos XML API for bootstraping through the TTY
    """

    def __init__(self, tty):
        self._tty = tty
        self.hello = None
        self.facts = Fact(self)

    # -------------------------------------------------------------------------
    # NETCONF session open and close
    # -------------------------------------------------------------------------

    def open(self, at_shell):
        """ start the XML API process and receive the 'hello' message """
        #print "\n **** inside tty_netconf open() ********"

        nc_cmd = ('junoscript', 'xml-mode')[at_shell]
        self._tty.write(nc_cmd + ' netconf need-trailer')

        while True:
            time.sleep(0.1)
            line = self._tty.read()
            if line.startswith("<!--"):
                break

        self.hello = self._receive()

    def close(self, force=False):
        """ issue the XML API to close the session """

        # if we do not have an open connection, then return now.
        #print "\n ******* inside tty_netconf close() ********"
        if force is False:
            if self.hello is None:
                return

        self.rpc('close-session')
        # removed flush

    # -------------------------------------------------------------------------
    # Junos OS configuration methods
    # -------------------------------------------------------------------------

    def load(self, content, **kvargs):
        """
        load-override a Junos 'conf'-style file into the device.  if the
        load is successful, return :True:, otherwise return the XML reply
        structure for further processing
        """
        #print "\n ********* inside tty_netconf load function *********"
        action = kvargs.get('action', 'override')
        #print "\n ****** action:", action
        cmd = E('load-configuration', dict(format='text', action=action),
                E('configuration-text', content)
                )
        #print "\n ***** cmd is: ******\n", etree.tostring(cmd)
        rsp = self.rpc(etree.tostring(cmd))
        #print "\n rsp in load is:", rsp
        val = rsp if rsp.findtext('.//ok') is None else True
        #print "return value of load is:", val
        return rsp if rsp.findtext('.//ok') is None else True

    def commit_check(self):
        """
        performs the Junos 'commit check' operation.  if successful return
        :True: otherwise return the response as XML for further processing.
        """
        #print "\n ****** inside tty_netconf commit_check function ************"
        rsp = self.rpc('<commit-configuration><check/></commit-configuration>')
        return True if 'ok' == rsp.tag else rsp

    def commit(self):
        """
        performs the Junos 'commit' operation.  if successful return
        :True: otherwise return the response as XML for further processing.
        """
        #print "\n ******** inside tty_netconf commit() function *********"
        rsp = self.rpc('<commit-configuration/>')
        if 'ok' == rsp.tag:
            return True     # some devices use 'ok'
        if len(rsp.xpath('.//commit-success')) > 0:
            return True
        return rsp

    def rollback(self):
        """ rollback that recent changes """
        #print "\n ******** inside tty_netconf rollback() function *****"
        cmd = E('load-configuration', dict(compare='rollback', rollback="0"))
        return self.rpc(etree.tostring(cmd))

    # -------------------------------------------------------------------------
    # MISC device commands
    # -------------------------------------------------------------------------

    def reboot(self, in_min=0):
        """ issue a reboot to the device """
        print "\n ******** inside tty_netconf reboot function ****\n "
        cmd = E('request-reboot', E('in', str(in_min)))
        print "\n reboot etree.tostring(cmd)", etree.tostring(cmd)
        rsp = self.rpc(etree.tostring(cmd))
        return True

    def poweroff(self, in_min=0):
        """ issue a reboot to the device """
        print "\n ******** inside tty_netconf poweroff ****\n"
        cmd = E('request-power-off', E('in', str(in_min)))
        print "\n poweroff etree.tostring(cmd)", etree.tostring(cmd)
        rsp = self.rpc(etree.tostring(cmd))
        return True

    def zeroize(self, value):
        """ issue a reboot to the device """
        #print "\n ******** inside tty_netconf zeroize ******\n"
        if value in ["local", "media"]:
            cmd_value = "request system zeroize " + value
        else:
            cmd_value = "request system zeroize"
        #print "\n cmd_value: ", cmd_value
        cmd = E.command(cmd_value)
        #print "\n cmd: ", cmd
        try:
            rsp = self.rpc(etree.tostring(cmd))
            #print "\n **** zeroize rsp is: ", rsp
        except:
            pass
            #print "\n **** inside except ****"
        return True

    def enablecluster(self, cluster_id, node):
        """ issue request chassis cluster command """
        #print "\n ******** inside tty_netconf enablecluster *********\n "
        cmd = E('set-chassis-cluster-enable', E('cluster-id', str(cluster_id)), E('node', str(node)), E('reboot'))
        rsp = self.rpc(etree.tostring(cmd))
        #device will be set to new cluster ID:NODE value
        return True

    def disablecluster(self):
        """ issue set chassis cluster disable to the device nad reboot """
        #print "\n ******** inside tty_netconf disablecluster ****\n "
        cmd = E.command('set chassis cluster disable reboot')
        rsp = self.rpc(etree.tostring(cmd))
        # No need to check error exception, device will be rebooted even if not in cluster
        return True

    # -------------------------------------------------------------------------
    # XML RPC command execution
    # -------------------------------------------------------------------------

    def rpc(self, cmd):
        """
        Write the XML cmd and return the response as XML object.

        :cmd:
          <str> of the XML command.  if the :cmd: is not XML, then
          this routine will perform the brackets; i.e. if given
          'get-software-information', this routine will turn
          it into '<get-software-information/>'

        NOTES:
          The return XML object is the first child element after
          the <rpc-reply>.  There is also no error-checking
          performing by this routine.
        """
        #print "\n ******* cmd is: ", cmd
        #print "\n ******** inside tty_netconf rpc() \n "
        if not cmd.startswith('<'):
            cmd = '<{0}/>'.format(cmd)
        #print "\n ****** rpc is:", '<rpc>{0}</rpc>'.format(cmd)
        self._tty.rawwrite('<rpc>{0}</rpc>'.format(cmd))
        rsp = self._receive()
        #print "\n ***** rsp and its type and length :", rsp, type(rsp), len(rsp)
        #print "\n ****** rpc reply:", etree.tostring(rsp)
        #print "\n ******* return value in tty_netconf rpc function: ", rsp, rsp[0]
        return rsp[0]  # return first child after the <rpc-reply>

    # -------------------------------------------------------------------------
    # LOW-LEVEL I/O for reading back XML response
    # -------------------------------------------------------------------------

    def _receive(self):
        """ process the XML response into an XML object """
        #print "\n ******** inside tty_netconf _receive() ****\n "
        rxbuf = []
        wait_time = 0
        while True:
            line = self._tty.read().strip()
            #print "\n ******* line:", line
            if not line:
                #print "\n ****** inside not line *******"
                time.sleep(0.5)
                wait_time += 0.5
                if wait_time > 3:
                    print "\n waiting ......"
                    break
                else:
                    print "\n Continuing......"
                    continue                       # if we got nothin, go again
            if _NETCONF_EOM == line:
                break              # check for end-of-message
            rxbuf.append(line)

            #print "\n ************* rxbuf:", rxbuf

        rxbuf[0] = _xmlns_strip(rxbuf[0])         # nuke the xmlns
        #print "\n rxbuf[0]", rxbuf[0]

        rxbuf[1] = _xmlns_strip(rxbuf[1])         # nuke the xmlns
        #print "\n ***** rxbuf[1]", rxbuf[1]

        rxbuf = map(_junosns_strip, rxbuf)        # nuke junos: namespace
        #print "\n ********* rxbuf:", rxbuf

        try:
            as_xml = etree.XML(''.join(rxbuf))
            return as_xml
        except:
            #### length of return value should be atleast one, need atleast two nodes for length >=1
            if '</xnm:error>' in rxbuf:
                for x in rxbuf:
                    if '<message>' in x:
                        return etree.XML('<error-in-receive>' + x + '</error-in-receive>')
            else:
                return etree.XML('<error-in-receive> <message> no message </message> </error-in-receive>')



"""

        try:
            print "\n inside try block"
            for val in rxbuf:
                obj = re.search(r'\<.*\>', val)
                print "\n ***** obj is: ", obj
                if obj:
                    rxbuf1.append(obj.group())
                    print "\n *****rxbuf1", rxbuf1
                    as_xml = etree.XML(''.join(rxbuf1))
            print "\n ******** as_xml:", as_xml
            return as_xml
        except:
            print "\n ******* inside except of _receive of tty_netconf \n"
            if '</xnm:error>' in rxbuf:
                for x in rxbuf:
                    if '<message>' in x:
                        return etree.XML('<error-in-receive>' + x + '</error-in-receive>')
            else:
                return etree.XML('<error-in-receive/>')

"""
