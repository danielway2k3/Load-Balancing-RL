import requests
import time
import json
import numpy as np
from monitoring import Monitor
from dqn_agent import DQNAgent

class SDNController:
    def __init__(self):
        self.monitor = Monitor()
        self.agent = DQNAgent()
        self.hosts = {0: 'h1', 1: 'h2', 2: 'h3'}
        self.host_ips = {0: '10.0.0.1', 1: '10.0.0.2', 2: '10.0.0.3'}
        self.lb_ip = '10.0.0.100'
        self.client_ip = '10.0.0.99'
        self.controller_api = 'http://localhost:8080/stats/flowentry/add'

    def set_flow_rules(self, target_host):
        """Set OpenFlow rules via Ryu REST API to direct traffic to the target host"""
        # Convert host name to index if a string is provided
        if isinstance(target_host, str):
            # Find the index for this host name
            target_host_idx = next((idx for idx, name in self.hosts.items() if name == target_host), None)
            if target_host_idx is None:
                print(f"Error: Host {target_host} not found")
                return False
        else:
            target_host_idx = target_host
            
        try:
            target_ip = self.host_ips[target_host_idx]
            target_port = target_host_idx + 1  # Port numbers start from 1

            # Delete existing flow rules
            self.delete_flow_rules()
            
            # Các URL Ryu REST API tiêu chuẩn
            add_url = 'http://localhost:8080/stats/flowentry/add'
            
            # Add flow rule from load balancer to server (target_host)
            flow_rule = {
                'dpid': 1,
                'priority': 32768,
                'match': {
                    'in_port': 4,
                    'eth_type': 0x0800,
                    'ipv4_src': self.lb_ip,
                    'ipv4_dst': target_ip
                },
                'actions': [
                    {
                        'type': 'OUTPUT',
                        'port': target_port
                    }
                ],
                'idle_timeout': 300
            }
            
            response = requests.post(add_url, json=flow_rule)
            if response.status_code != 200:
                print(f"Error setting flow rule: {response.text}")
                print("Continuing training despite API error")
            else:
                print(f"Flow rule set to direct traffic to {self.hosts[target_host_idx]}")
                
            return True  # Luôn trả về True để training có thể tiếp tục
        
        except Exception as e:
            print(f"Error setting flow rule: {e}")
            print("Continuing training in simulation mode")
            return True  # Tiếp tục training
    def delete_flow_rules(self):
        """Delete all existing flow rules"""
        try:
            delete_url = 'http://localhost:8080/stats/flowentry/delete'
            
            flow_rule = {
                'dpid': 1
            }
            
            response = requests.post(delete_url, json=flow_rule)
            if response.status_code != 200:
                print(f"Error deleting flow rules: {response.text}")
                print("Continuing training process despite API error")
            else:
                print("All flow rules deleted")
            return True  # Luôn trả về True để tiếp tục quá trình training
        except requests.exceptions.ConnectionError:
            print("ERROR: Cannot connect to Ryu controller API")
            print("Continuing training process in simulation mode")
            return True  # Tiếp tục training

    def _generate_traffic(self):
        """Mô phỏng việc tạo lưu lượng truy cập thử nghiệm"""
        print("Simulating test traffic generation...")
        
        time.sleep(2)  # Giả lập thời gian tạo lưu lượng
        
    def save_rewards(self, rewards, filename):
        """Lưu rewards vào file CSV"""
        import pandas as pd
        df = pd.DataFrame({'episode': range(1, len(rewards) + 1), 'reward': rewards})
        df.to_csv(filename, index=False)
        print(f"Rewards saved to {filename}")

    def calculate_reward(self, host, metrics):
        """Calculate reward based on performance metrics of the selected host
        
        A good load balancing strategy should:
        1. Favor hosts with low latency (faster response)
        2. Favor hosts with high throughput (more capacity)
        3. Avoid hosts with high CPU usage (prevent overload)
        4. Consider load distribution across all hosts
        """
        # Get metrics for the selected host
        host_metrics = metrics[host]
        latency = host_metrics['latency']
        throughput = host_metrics['throughput']
        cpu = host_metrics['cpu']
        
        # Normalize values to 0-1 range
        norm_latency = min(1.0, latency / 200.0)  # Lower is better
        norm_throughput = min(1.0, throughput / 10.0)  # Higher is better
        norm_cpu = cpu / 100.0  # Lower is better
        
        # Calculate raw reward components
        latency_reward = 1.0 - norm_latency  # Invert so lower latency gives higher reward
        throughput_reward = norm_throughput  # Higher throughput gives higher reward
        cpu_reward = 1.0 - norm_cpu  # Invert so lower CPU gives higher reward
        
        # Weighted sum of components
        # You can adjust these weights to prioritize different aspects
        reward = (0.3 * latency_reward + 
                0.4 * throughput_reward + 
                0.3 * cpu_reward)
        
        # Additional penalty for very high CPU usage (>80%)
        if cpu > 80.0:
            reward -= 0.5
        
        # Check load distribution - penalize if one host is consistently overloaded
        avg_cpu = sum(metrics[h]['cpu'] for h in self.hosts.values()) / len(self.hosts)
        if cpu > 1.5 * avg_cpu:  # This host is much more loaded than average
            reward -= 0.3
        
        return reward * 10  # Scale reward to make it more significant
    
    def train(self, episodes=30, batch_size=32):
        """Train the DQN agent"""
        print("Starting DQN training...")
        
        self.monitor.simulation_mode = True
        print("Using simulated network metrics for training")
        
        # Tiếp tục huấn luyện ngay cả khi kiểm tra thất bại
        print("Using simulated network metrics for training")
        
        rewards = []
        best_reward = float('-inf')
        no_improve = 0
        
        for episode in range(episodes):
            print(f"\nEpisode {episode+1}/{episodes}")
            
            # Thu thập dữ liệu ban đầu
            metrics = self.monitor.collect_data()
            
            # Xử lý state
            state = self.preprocess_state(metrics)
            
            # Chọn action (host)
            action = self.agent.act(state)
            host = self.hosts[action]
            
            print(f"Selected host: {host}")
            
            # Thiết lập flow rules
            self.set_flow_rules(action)
            
            # Đợi một chút để thực hiện flow rules
            time.sleep(2)
            
            # Thu thập dữ liệu mới
            next_metrics = self.monitor.collect_data()
            next_state = self.preprocess_state(next_metrics)
            
            # Tính reward
            reward = self.calculate_reward(host, next_metrics)
            print(f"Reward: {reward:.2f}")
            
            done = (episode == episodes - 1)
            self.agent.remember(state, action, reward, next_state, done)
            
            # Huấn luyện mô hình
            self.agent.replay(batch_size)
            
            # Cập nhật mô hình mục tiêu định kỳ
            if episode % 5 == 0:
                self.agent.update_target_model()
                
            print(f"Epsilon: {self.agent.epsilon:.4f}")
            
            # Dọn dẹp cho tập tiếp theo
            self.delete_flow_rules()
            time.sleep(1)
        
            if reward > best_reward:
                best_reward = reward
                no_improve = 0
                self.agent.save('best_model.pth')
            else:
                no_improve += 1
                
            rewards.append(reward)
            
            # # Kiểm tra dừng sớm
            # if no_improve >= 15:
            #     print("Early stopping due to no improvement")
            #     break
                
        # Lưu kết quả huấn luyện
        self.save_rewards(rewards, 'rewards.csv')
        self.monitor.save_data('monitoring_data.csv')
        
        return rewards

    def run(self, model_path="dqn_load_balancer.pth"):
        """Run the load balancer with the trained model"""
        print("Running load balancer with DQN agent...")
        
        # Load the trained model
        try:
            self.agent.load(model_path)
            print(f"Loaded model from {model_path}")
            self.agent.epsilon = 0.01  # Set exploration rate to minimum for deployment
        except:
            print(f"Could not load model from {model_path}, using untrained model")
        
        while True:
            try:
                print("\nCollecting current metrics...")
                metrics = self.monitor.collect_data()
                state = self.agent.preprocess_state(metrics)
                
                print("State vector:", state)
                
                # Choose best action
                action = self.agent.act(state)
                host = self.hosts[action]
                print(f"Selected optimal host: {host}")
                
                # Execute action
                self.set_flow_rules(action)
                
                # Wait before next decision
                time.sleep(30)
                
            except KeyboardInterrupt:
                print("Load balancer stopped by user")
                self.delete_flow_rules()
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(5)
                
    def preprocess_state(self, metrics):
        """Chuyển đổi metrics thành vector state cho DQN agent"""
        state = []
        
        # Chuẩn hóa metrics cho từng host - sử dụng giá trị của từ điển hosts
        for host_idx, host_name in self.hosts.items():
            # Chuẩn hóa latency (giả sử tối đa 200ms)
            norm_latency = min(1.0, metrics[host_name]['latency'] / 200.0)
            
            # Chuẩn hóa throughput (giả sử tối đa 10 Mbps)
            norm_throughput = min(1.0, metrics[host_name]['throughput'] / 10.0)
            
            # Chuẩn hóa CPU usage (đã ở thang đo 0-100)
            norm_cpu = metrics[host_name]['cpu'] / 100.0
            
            # Thêm vào state vector
            state.extend([norm_latency, norm_throughput, norm_cpu])
        
        return np.array(state)