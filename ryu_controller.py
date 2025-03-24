from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, arp
from ryu.app.wsgi import WSGIApplication
from ryu.lib import hub
from webob import Response
import json
from ryu.app.ofctl_rest import RestStatsApi


class LoadBalancerController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(LoadBalancerController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.server_ips = {
            '10.0.0.1': 1,  # h1
            '10.0.0.2': 2,  # h2
            '10.0.0.3': 3   # h3
        }
        self.lb_ip = '10.0.0.100'
        self.client_ip = '10.0.0.99'
        self.flow_rules = []
        
        # Tham chiếu đến ứng dụng WSGI
        wsgi = kwargs['wsgi']
        wsgi.register(RESTController, {'load_balancer_app': self})
        
        # Khởi động thread giám sát datapath
        self.monitor_thread = hub.spawn(self._monitor)
    
    def _monitor(self):
        """Monitor datapath connections"""
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(10)
    
    def _request_stats(self, datapath):
        """Request flow stats from datapath"""
        self.logger.debug('Sending stats request to datapath %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)
    
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.info('Register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.info('Unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]
    
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        try:
            datapath = ev.msg.datapath
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser

            # Install table-miss flow entry
            match = parser.OFPMatch()
            actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                            ofproto.OFPCML_NO_BUFFER)]
            self.add_flow(datapath, 0, match, actions)
            
            # Add default forwarding rules
            self._add_default_flows(datapath)
            
            self.logger.info(f"Switch {datapath.id} configured with default flows")
            
        except Exception as e:
            self.logger.error(f"Error configuring switch: {e}")
            raise
        
    def _add_default_flows(self, datapath):
        """Add basic connectivity flows"""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto  # Add this line to get ofproto
        
        # Allow all ARP
        match = parser.OFPMatch(eth_type=0x0806)  # ARP
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
        self.add_flow(datapath, 1, match, actions)
        
        # Allow IPv4 between known hosts
        for src_ip in self.server_ips.keys():
            for dst_ip in [self.lb_ip, self.client_ip]:
                match = parser.OFPMatch(
                    eth_type=0x0800,  # IPv4
                    ipv4_src=src_ip,
                    ipv4_dst=dst_ip
                )
                actions = [parser.OFPActionOutput(ofproto.OFPP_NORMAL)]
                self.add_flow(datapath, 1, match, actions)
    
    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst, idle_timeout=idle_timeout, 
                                    hard_timeout=hard_timeout)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst,
                                    idle_timeout=idle_timeout, hard_timeout=hard_timeout)
        datapath.send_msg(mod)
    
    def delete_all_flows(self, datapath):
        """Delete all flows from datapath"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Delete all flow rules except the table-miss entry
        match = parser.OFPMatch()
        instructions = []
        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=match,
            instructions=instructions
        )
        datapath.send_msg(flow_mod)
        
        # Reinstall table-miss flow entry
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                         ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
    
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handle packet in messages from the switch"""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # Ignore LLDP packets
            return
        
        dst_mac = eth.dst
        src_mac = eth.src
        
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        
        # Learn MAC address to avoid FLOOD
        self.mac_to_port[dpid][src_mac] = in_port
        
        # Handle ARP packets specially
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            self._handle_arp(datapath, in_port, pkt)
            return
            
        # Handle IPv4 packets
        ip_header = pkt.get_protocol(ipv4.ipv4)
        if ip_header:
            self._handle_ipv4(datapath, in_port, ip_header, pkt)
            return
            
        # Default behavior for other packets: learn and flood if needed
        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD
        
        actions = [parser.OFPActionOutput(out_port)]
        
        # Install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac)
            self.add_flow(datapath, 1, match, actions, idle_timeout=30)
        
        # Send packet out to handle current packet
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
            
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
    
    def _handle_ipv4(self, datapath, in_port, ip_header, pkt):
        """Handle IPv4 packets"""
        parser = datapath.ofproto_parser
        
        # Learn source MAC and IP for future use
        eth = pkt.get_protocol(ethernet.ethernet)
        src_mac = eth.src
        dst_mac = eth.dst
        src_ip = ip_header.src
        dst_ip = ip_header.dst
        
        # Forward based on learned MAC information
        dpid = datapath.id
        
        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
            actions = [parser.OFPActionOutput(out_port)]
            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                   ipv4_src=src_ip,
                                   ipv4_dst=dst_ip)
            
            self.add_flow(datapath, 2, match, actions, idle_timeout=30)
            
            # Send packet out
            self._send_packet_out(datapath, pkt, in_port, out_port)
    
    def _send_packet_out(self, datapath, pkt, in_port, out_port):
        """Send a packet out to the specified port"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        pkt.serialize()
        data = pkt.data
        actions = [parser.OFPActionOutput(out_port)]
        
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=ofproto.OFP_NO_BUFFER,
                                 in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
    
    def add_flow_rule(self, rule):
        """Add a flow rule from API request"""
        dp_id = rule.get('datapath_id', 1)
        datapath = self.datapaths.get(dp_id)
        
        if not datapath:
            self.logger.error(f"Datapath {dp_id} not found")
            return False
        
        # Create match and actions
        parser = datapath.ofproto_parser
        priority = rule.get('priority', 32768)
        
                # Build match
        match_dict = {'eth_type': ether_types.ETH_TYPE_IP}
        
        if 'in_port' in rule:
            match_dict['in_port'] = int(rule['in_port'])
        if 'ipv4_src' in rule:
            match_dict['ipv4_src'] = rule['ipv4_src']
        if 'ipv4_dst' in rule:
            match_dict['ipv4_dst'] = rule['ipv4_dst']
            
        match = parser.OFPMatch(**match_dict)
        
        # Build action
        output_port = int(rule['output_port'])
        actions = [parser.OFPActionOutput(output_port)]
        
        if 'qos' in rule:
            qos_config = {
                'max_rate': rule.get('max_rate', '10M'),
                'min_rate': rule.get('min_rate', '1M'),
                'brust': rule.get('brust', '1M')
            }
            actions.append(parser.OFPActionSetQueue(rule.get('queue_id', 1)))
        
        # Add flow
        idle_timeout = rule.get('idle_timeout', 0)
        hard_timeout = rule.get('hard_timeout', 0)
        
        self.add_flow(datapath, priority, match, actions, 
                     idle_timeout=idle_timeout, hard_timeout=hard_timeout)
        
        # Store rule
        self.flow_rules.append(rule)
        return True
    
    def delete_all_flow_rules(self):
        """Delete all flow rules from all datapaths"""
        for dp_id, datapath in self.datapaths.items():
            self.delete_all_flows(datapath)
        
        # Clear flow rules list
        self.flow_rules = []
        return True


class RESTController(object):
    """REST API handler for the load balancer controller"""
    
    def __init__(self, req, link, data, **config):
        self.load_balancer_app = data['load_balancer_app']
        
    def make_response(self, status, body):
        """Create a REST API response"""
        body = json.dumps(body)
        return Response(content_type='application/json', body=body, status=status)
    
    def GET(self, req, **kwargs):
        """Handle GET requests to get flow rules"""
        body = {
            'flow_rules': self.load_balancer_app.flow_rules
        }
        return self.make_response(200, body)
    
    def POST(self, req, **kwargs):
        """Handle POST requests to add flow rules"""
        try:
            rule = req.json if req.body else {}
            result = self.load_balancer_app.add_flow_rule(rule)
            
            if result:
                body = {'status': 'success', 'rule': rule}
                status = 200
            else:
                body = {'status': 'error', 'message': 'Failed to add flow rule'}
                status = 400
                
            return self.make_response(status, body)
            
        except Exception as e:
            body = {'status': 'error', 'message': str(e)}
            return self.make_response(500, body)
    
    def DELETE(self, req, **kwargs):
        """Handle DELETE requests to delete flow rules"""
        try:
            result = self.load_balancer_app.delete_all_flow_rules()
            
            if result:
                body = {'status': 'success', 'message': 'All flow rules deleted'}
                status = 200
            else:
                body = {'status': 'error', 'message': 'Failed to delete flow rules'}
                status = 400
                
            return self.make_response(status, body)
            
        except Exception as e:
            body = {'status': 'error', 'message': str(e)}
            return self.make_response(500, body)