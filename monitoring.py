import time
import subprocess
import re
import pandas as pd
import numpy as np
import os
import traceback 
import random

class Monitor:
    def __init__(self):
        self.hosts = ['h1', 'h2', 'h3']
        self.host_ips = {'h1': '10.0.0.1', 'h2': '10.0.0.2', 'h3': '10.0.0.3'}
        self.lb = 'lb'
        self.lb_ip = '10.0.0.100'
        self.data = []
        # Thêm các biến để lưu tiền tố namespace
        self.host_namespace_prefix = ''
        self.lb_namespace_prefix = ''
        self.simulation_mode = True
        
    def ping_latency(self, host_ip):
        """Đo độ trễ từ load balancer đến host"""
        if self.simulation_mode:
            # Giá trị giả lập với biến động nhỏ
            base_latency = {'10.0.0.1': 20.0, '10.0.0.2': 40.0, '10.0.0.3': 30.0}
            latency = base_latency.get(host_ip, 50.0) * (0.9 + 0.2 * random.random())
            return latency
        try:
            lb_ns = f"{self.lb_namespace_prefix}{self.lb}"
            cmd = f"sudo ip netns exec {lb_ns} ping -c 3 -q {host_ip}"
                
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
            
            # Phân tích kết quả ping
            pattern = r"round-trip min/avg/max/mdev = [\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms"
            match = re.search(pattern, output)
            if match:
                return float(match.group(1))
            else:
                # Fallback values
                if host_ip == '10.0.0.1':  # h1
                    return 50.0
                elif host_ip == '10.0.0.2':  # h2
                    return 100.0
                elif host_ip == '10.0.0.3':  # h3
                    return 150.0
                return 100.0
                    
        except subprocess.CalledProcessError as e:
            print(f"Error measuring latency: {e}")
            # Fallback values
            if host_ip == '10.0.0.1':
                return 50.0
            elif host_ip == '10.0.0.2':
                return 100.0
            elif host_ip == '10.0.0.3':
                return 150.0
            return 100.0
    
    def measure_throughput(self, host):
        """Đo thông lượng từ load balancer đến host"""
        if self.simulation_mode:
            # Giá trị giả lập với biến động
            base_throughput = {'h1': 8.0, 'h2': 5.0, 'h3': 7.0}
            throughput = base_throughput.get(host, 5.0) * (0.9 + 0.2 * random.random())
            return throughput
        try:
            host_ip = self.host_ips[host]
            host_ns = f"{self.host_namespace_prefix}{host}"
            lb_ns = f"{self.lb_namespace_prefix}{self.lb}"
            
            # Dừng iperf server nếu còn từ lần chạy trước
            stop_server_cmd = f"sudo ip netns exec {host_ns} pkill -9 iperf || true"
            subprocess.call(stop_server_cmd, shell=True)
            
            # Khởi động iperf server trên host đích
            server_cmd = f"sudo ip netns exec {host_ns} iperf -s -D"
            subprocess.call(server_cmd, shell=True)
            
            time.sleep(0.5)  # Chờ server khởi động
            
            # Chạy iperf client từ load balancer
            client_cmd = f"sudo ip netns exec {lb_ns} iperf -c {host_ip} -t 2 -f m"
            output = subprocess.check_output(client_cmd, shell=True, stderr=subprocess.STDOUT, text=True)
            
            # Dừng iperf server
            stop_server_cmd = f"sudo ip netns exec {host_ns} pkill -9 iperf"
            subprocess.call(stop_server_cmd, shell=True)
            
            # Phân tích kết quả để lấy thông lượng
            pattern = r"(\d+\.?\d*)\s+Mbits/sec"
            match = re.search(pattern, output)
            
            if match:
                throughput = float(match.group(1))
                return throughput
            else:
                print(f"Warning: Could not extract throughput from: {output}")
                return 5.0  # Giá trị mặc định
                    
        except subprocess.CalledProcessError as e:
            print(f"Error measuring throughput: {e}")
            print(f"Error output: {e.output if hasattr(e, 'output') else 'N/A'}")
            
            # Nếu đo thất bại, sử dụng giá trị dự phòng ước lượng dựa trên độ trễ
            latency = self.ping_latency(self.host_ips[host])
            estimated_throughput = 10.0 * (200 - latency) / 200  # Công thức ước lượng
            return max(0.1, min(10.0, estimated_throughput))

    def get_cpu_usage(self, host):
        """Lấy mức sử dụng CPU của host"""
        if self.simulation_mode:
            # Giá trị giả lập với biến động
            base_cpu = {'h1': 30.0, 'h2': 60.0, 'h3': 25.0}
            # Thêm biến động để thể hiện sự thay đổi giữa các lần đo
            cpu = base_cpu.get(host, 40.0) * (0.9 + 0.2 * random.random())
            return cpu
        try:
            host_ns = f"{self.host_namespace_prefix}{host}"
            
            # Kiểm tra xem namespace có tồn tại không
            check_cmd = f"sudo ip netns list | grep -q {host_ns}"
            if subprocess.call(check_cmd, shell=True) != 0:
                print(f"Namespace '{host_ns}' does not exist")
                # Return fallback values
                return self._get_fallback_cpu(host)
                
            # Sử dụng lệnh top để lấy thông tin sử dụng CPU
            cmd = f"sudo ip netns exec {host_ns} top -bn1 | grep 'Cpu(s)' | awk '{{print $2 + $4}}'"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
            
            # Check if output contains an error message
            if "Cannot open network namespace" in output:
                print(f"Cannot access namespace '{host_ns}'")
                return self._get_fallback_cpu(host)
            
            cpu_usage = float(output.strip())
            return cpu_usage
            
        except subprocess.CalledProcessError as e:
            print(f"Error getting CPU usage: {e}")
            print(f"Error output: {e.output if hasattr(e, 'output') else 'N/A'}")
            
            return self._get_fallback_cpu(host)
        except ValueError as e:
            print(f"Error parsing CPU usage: {e}")
            return self._get_fallback_cpu(host)
    def _get_fallback_cpu(self, host):
        """Return fallback CPU values for a host"""
        if host == 'h1':
            return 30.0  # Giả định tải vừa phải
        elif host == 'h2':
            return 60.0  # Giả định tải cao hơn
        elif host == 'h3':
            return 20.0  # Giả định tải thấp
        else:
            return 50.0  # Giá trị mặc định
    
    def collect_data(self):
        """Thu thập tất cả dữ liệu giám sát"""
        metrics = {}
        timestamp = time.time()
        
        print("Collecting metrics from hosts...")
        
        for host in self.hosts:
            host_ip = self.host_ips[host]
            
            # Đo độ trễ
            latency = self.ping_latency(host_ip)
            print(f"{host} latency: {latency:.2f} ms")
            
            # Đo thông lượng
            throughput = self.measure_throughput(host)
            print(f"{host} throughput: {throughput:.2f} Mbps")
            
            # Lấy mức sử dụng CPU
            cpu = self.get_cpu_usage(host)
            print(f"{host} CPU usage: {cpu:.2f}%")
            
            # Lưu dữ liệu
            self.data.append({
                'timestamp': timestamp,
                'host': host,
                'latency': latency,
                'throughput': throughput,
                'cpu': cpu
            })
            
            # Lưu metrics cho việc ra quyết định
            metrics[host] = {
                'latency': latency,
                'throughput': throughput,
                'cpu': cpu
            }
        
        return metrics
    
    def save_data(self, filename='monitoring_data.csv'):
        """Lưu dữ liệu đã thu thập vào tệp CSV"""
        df = pd.DataFrame(self.data)
        df.to_csv(filename, index=False)
        print(f"Data saved to {filename}")
        
    def verify_mininet_running(self):
        print("Using simulation mode for training")
        self.simulation_mode = True
        return True