from mininet.net import Mininet
from mininet.node import Controller, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.link import TCLink
from mininet.topo import Topo
import os

class LoadBalancerTopo(Topo):
    def build(self):
        # Tạo switch
        s1 = self.addSwitch('s1')
        
        # Tạo các host server
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')
        h3 = self.addHost('h3', ip='10.0.0.3/24')
        
        # Tạo load balancer và client
        lb = self.addHost('lb', ip='10.0.0.100/24')
        client = self.addHost('client', ip='10.0.0.99/24')
        
        # Tạo các liên kết với độ trễ khác nhau
        self.addLink(h1, s1, cls=TCLink, delay='50ms')
        self.addLink(h2, s1, cls=TCLink, delay='100ms')
        self.addLink(h3, s1, cls=TCLink, delay='150ms')
        self.addLink(lb, s1, cls=TCLink, delay='20ms')
        self.addLink(client, s1, cls=TCLink, delay='10ms')

def start_network():
    # Thiết lập log level
    setLogLevel('info')
    
    # Tạo topology
    topo = LoadBalancerTopo()
    
    # Tạo mạng với Ryu controller
    net = Mininet(topo=topo, link=TCLink, controller=RemoteController('c0', ip='127.0.0.1', port=6653))
    
    # Khởi động mạng
    net.start()
    # Create symlinks for easier access
    print("Creating namespace symlinks...")
    for host in net.hosts:
        cmd = f"sudo ln -sf /var/run/netns/mn-{host.name} /var/run/netns/{host.name}"
        os.system(cmd)
        print(f"Created symlink for {host.name}")
    print("Congiguring nerwork...")
    
    for host in net.hosts:
        host.cmd('ip link set dev lo up')
    
    # Configure load balancer
    lb = net.get('lb')
    lb.cmd('ip route add default via 10.0.0.100')
    
    # Configure client
    client = net.get('client')
    client.cmd('ip route add default via 10.0.0.99')
    
    # Configure servers
    h1 = net.get('h1')
    h1.cmd('ip route add default via 10.0.0.1')
    
    h2 = net.get('h2')
    h2.cmd('ip route add default via 10.0.0.2')
    
    h3 = net.get('h3')
    h3.cmd('ip route add default via 10.0.0.3')
    
    # Wait for network to settle
    print("Waiting for network to settle...")
    net.waitConnected()
    
    print("Network configuration completed")
    print("Try 'pingall' to test connectivity")
    
    # Mở CLI và chờ người dùng thoát
    CLI(net)
    
    print("Mininet CLI closed. Network is still running.")
    print("You can now run: python3 load_balancer.py --mode train --episodes 30")
    
    # Không dừng mạng để có thể chạy script load_balancer
    # Mạng sẽ tiếp tục chạy cho đến khi script kết thúc

if __name__ == '__main__':
    start_network()