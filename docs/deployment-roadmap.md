# Deployment roadmap: Current state to public Hetzner service

*What actually needs to be built*

## Current state (verified)

**Simulator:**
- Runs locally via `python tools/simulator_manager.py`
- In-memory state only (no persistence)
- Single-user (one simulator per machine)
- Protocols bind to localhost or 0.0.0.0
- No authentication/authorization
- No multi-tenancy
- No automatic reset capability
- 247MB project size

**Dependencies:**
- Python 3.12
- 20+ protocol libraries (pymodbus, asyncua, snap7, etc.)
- No containerization
- No web interface
- No user management

**Access:**
- Requires local Python installation
- Requires cloning repository
- Requires running scripts via command line
- No remote access mechanism

## Target state

**Public service on Hetzner Cloud:**
- Anyone can access via web browser
- Each user gets isolated simulator instance
- Instances reset automatically (hourly/daily)
- Available 24/7, not just during workshops
- Multiple concurrent users
- Secure access (no exposing attack surface to internet)
- Cost-effective operation

## What needs to be built

### 1. Containerisation

**Create Dockerfile:**
- Base image: python:3.12-slim
- Install all dependencies from requirements.txt
- Copy simulator code
- Expose required ports (102, 502, 4840, 20000, 44818, 2404)
- Entry point: simulator_manager.py

**Verify:**
- All protocols work in container
- Port mappings correct
- Logs accessible outside container

**Effort:** 1-2 days

**Deliverables:**
- `Dockerfile`
- `docker-compose.yml` for testing
- Documentation for building image

### 2. State reset mechanism

**Currently:** State persists until manual restart

**Needs:**
```python
# Add to simulator_manager.py
async def reset_simulator():
    """Reset simulator to initial vulnerable state."""
    # Stop all protocol servers
    # Clear SystemState
    # Clear DataStore
    # Reset physics engines
    # Restart protocol servers
```

**Trigger options:**
- Timer-based (every N minutes)
- HTTP endpoint (/reset)
- CLI command (docker exec ... reset)

**Effort:** 1 day

**Deliverables:**
- Reset function in simulator
- Configuration option for auto-reset interval
- HTTP endpoint for manual reset

### 3. Web terminal access

**Tech stack:**
- xterm.js (terminal emulator in browser)
- websockets (communication)
- Python backend (pty spawning)

**Implementation:**
```python
# web_terminal.py
import asyncio
import pty
import websockets

async def handle_terminal(websocket):
    # Spawn bash in pty
    # Forward stdin/stdout via websocket
    # Allow running attack scripts
```

**Frontend:**
```html
<!-- terminal.html -->
<div id="terminal"></div>
<script src="xterm.js"></script>
<script>
  const term = new Terminal();
  const ws = new WebSocket('ws://localhost:8080/terminal');
  // Connect terminal to websocket
</script>
```

**Effort:** 2-3 days

**Deliverables:**
- Web terminal server
- HTML frontend
- Integration with container
- Port 8080 for web access

### 4. User isolation and multi-tenancy

**Currently:** Single simulator per deployment

**Needs:**

**One container per user**
- Spawn new container for each user
- User connects to their container's web terminal
- Container auto-destroyed after N hours of inactivity
- Requires orchestration

**Orchestration needs:**
```python
# container_manager.py
class ContainerManager:
    async def create_user_instance(self, user_id: str) -> dict:
        """Spawn container for user, return connection details."""
        # docker run -d --name=user_{user_id} ...
        # Return: {url, ports, created_at}

    async def cleanup_idle_instances(self):
        """Remove containers idle > 2 hours."""

    async def get_active_instances(self) -> list:
        """List all running user containers."""
```

**Effort:** 3-4 days

**Deliverables:**
- Container orchestration script
- User instance lifecycle management
- Clean-up of idle instances
- Resource limits per container

### 5. Landing page and user flow

**User flow:**
1. Visit https://uu-power-light.org or a domain like that
2. Click "Start Hacking"
3. System spawns container (takes 10-30 seconds)
4. User gets web terminal connected to their simulator
5. User runs attack scripts
6. After 2 hours idle: container destroyed

**Landing page needs:**
```html
<!-- index.html -->
<h1>UU Power & Light Simulator</h1>
<p>Industrial control systems security training</p>
<button onclick="startSimulator()">Start Hacking</button>
<div id="status">Waiting...</div>
<div id="terminal" style="display:none;"></div>

<script>
async function startSimulator() {
  // Show status: "Starting your simulator..."
  const response = await fetch('/api/start');
  const {instance_id, terminal_url} = await response.json();
  // Show terminal
  connectTerminal(terminal_url);
}
</script>
```

**Backend API:**
```python
# api.py
@app.post("/api/start")
async def start_instance():
    instance_id = generate_id()
    container = await manager.create_user_instance(instance_id)
    return {
        "instance_id": instance_id,
        "terminal_url": f"/terminal/{instance_id}"
    }

@app.websocket("/terminal/{instance_id}")
async def terminal_ws(instance_id: str):
    # Connect to container's terminal
    # Forward websocket to container pty
```

**Effort:** 2 days

**Deliverables:**
- Landing page HTML/CSS/JS
- Backend API (FastAPI or Flask)
- Integration with container manager
- User-friendly error messages

### 6. Hetzner Cloud infrastructure

**What needs to be provisioned:**

**Server:**
- Hetzner CX41 or CX51 (4-8 vCPUs, 16-32GB RAM)
- Cost: €15-30/month
- Ubuntu 22.04 LTS
- Docker and Docker Compose installed
- Firewall configured

**Storage:**
- 50-100GB SSD (logs, container images)
- Container image caching

**Network:**
- Floating IP (static IP)
- Firewall rules:
  - Allow: 80 (HTTP), 443 (HTTPS), 22 (SSH)
  - Block: All OT protocol ports from internet (102, 502, 4840, etc.)
  - Internal: Containers can bind to 127.0.0.1, accessed via web terminal only

**DNS:**
- Point domain to Hetzner floating IP
- Let's Encrypt SSL certificate (via Certbot)

**Setup:**
```bash
# On Hetzner server
apt update && apt upgrade -y
apt install -y docker.io docker-compose nginx certbot python3-certbot-nginx

# Clone repository
git clone https://github.com/ninabarzh/power-and-light-sim.git
cd power-and-light-sim

# Build image
docker build -t uu-pl-sim:latest .

# Start orchestration service
python3 deployment/container_manager.py &

# Configure nginx reverse proxy
# Point uu-power-light.example.com to localhost:8080
# Get SSL certificate
certbot --nginx -d uu-power-light.org
```

**Effort:** 1 day (if experienced with Hetzner)

**Deliverables:**
- Hetzner account and server
- DNS configuration
- SSL certificate
- Nginx reverse proxy configuration
- Docker installed and configured

### 7. Monitoring and operations

**Essential monitoring:**
- How many containers running?
- CPU/RAM usage
- Disk space
- Containers stuck/crashed
- User activity

**Implementation:**
```python
# monitoring.py
@app.get("/api/stats")
async def get_stats():
    return {
        "active_instances": await manager.count_active(),
        "cpu_usage": get_cpu_usage(),
        "memory_usage": get_memory_usage(),
        "disk_usage": get_disk_usage(),
    }
```

**Dashboard (simple HTML):**
```html
<!-- admin.html -->
<h2>Admin Dashboard</h2>
<p>Active instances: <span id="active">0</span></p>
<p>CPU: <span id="cpu">0%</span></p>
<p>Memory: <span id="memory">0%</span></p>
<button onclick="cleanupAll()">Cleanup Idle</button>
```

**Alerting:**
- Disk space > 90%: Email alert
- Memory > 90%: Email alert
- Service down: Email alert
- Simple Python script checking every 5 minutes

**Effort:** 1-2 days

**Deliverables:**
- Monitoring endpoint
- Admin dashboard
- Alert script
- Log aggregation

### 8. Cost and resource management

**Resource limits per container:**
```yaml
# docker-compose.yml for user container
services:
  user-simulator:
    image: uu-pl-sim:latest
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
```

**Calculation:**
- Server: 8 vCPUs, 32GB RAM
- Per container: 0.5 CPU, 512MB RAM
- Max concurrent users: ~40-50
- Typical concurrent users: 5-10
- Cost: €30/month + domain (~€35/month total)

**If usage grows:**
- Scale vertically (bigger server)
- Or scale horizontally (multiple servers with load balancer)

**Effort:** Included in container orchestration

### 9. Documentation and maintenance

**User documentation:**
- Landing page: Quick start guide
- Challenge links (to existing workshop docs)
- FAQ (common issues)
- Contact/support info

**Admin documentation:**
- Deployment guide
- Backup procedures
- Update procedures
- Troubleshooting common issues
- Cost analysis

**Maintenance tasks:**
- Update dependencies (monthly)
- Update base Docker image (quarterly)
- Monitor costs (monthly)
- Review logs for abuse (weekly)
- Clean up old logs (automated)

**Effort:** 1-2 days (initial), 2-4 hours/month (ongoing)

## Work breakdown

### Phase 1: Make it deployable (1 week)
- Day 1-2: Dockerfile and containerisation
- Day 3: State reset mechanism
- Day 4-5: Web terminal implementation
- Day 6-7: Testing in local Docker

### Phase 2: Multi-tenancy (1 week)
- Day 1-2: Container orchestration
- Day 3-4: Landing page and API
- Day 5-7: Testing with multiple users locally

### Phase 3: Deploy to Hetzner (3 days)
- Day 1: Provision server, DNS, SSL
- Day 2: Deploy and configure
- Day 3: Monitoring and documentation

### Phase 4: Polish and launch (2-3 days)
- Day 1: Load testing
- Day 2: Security review
- Day 3: Documentation and announcement

**Total effort: 3-4 weeks**

## Technical decisions needed

### 1. Container orchestration

**Option A: Simple Python script**
- Pros: Easy to understand, no external dependencies
- Cons: Manual scaling, no HA
- Recommended for MVP

**Option B: Docker Swarm**
- Pros: Built-in orchestration, easier than Kubernetes
- Cons: Learning curve, overkill for single server

**Option C: Kubernetes**
- Pros: Industry standard, scales infinitely
- Cons: Massive overkill, complexity nightmare

**Recommendation: Start with Option A**

### 2. User persistence

**Option A: No persistence (stateless)**
- Container destroyed after timeout
- No user accounts
- Simple but can't save progress

**Option B: Optional save/restore**
- User gets unique ID
- Can save state to S3/storage
- Can restore later
- More complex

**Recommendation: Start with Option A, add Option B later if requested**

### 3. Access control

**Option A: Public, no auth**
- Anyone can start instance
- Risk of abuse (crypto mining, proxying)
- Simple

**Option B: Email-gated**
- Enter email to start
- Rate limit per email
- Reduces abuse

**Option C: Full auth**
- User accounts, login
- Complex, overkill

**Recommendation: Start with Option A, add Option B if abused**

## Risks and mitigations

**Risk: Crypto mining**
- CPU limits per container (0.5 CPU)
- Monitor CPU usage patterns
- Ban IPs with sustained high CPU

**Risk: Using as proxy/attack platform**
- Don't expose OT protocol ports to internet
- Only web terminal accessible externally
- Log all activity
- Ban abusive IPs

**Risk: Running out of resources**
- Hard limits per container
- Max N containers total
- Queue if at capacity

**Risk: Costs spiral**
- Set budget alerts in Hetzner
- Monitor monthly costs
- Auto-shutdown if costs exceed threshold

**Risk: Service goes down**
- Simple monitoring and alerts
- Document recovery procedures
- Accept occasional downtime (not mission-critical)

## Post-launch operations

**Weekly:**
- Review logs for abuse
- Check resource usage
- Verify backups

**Monthly:**
- Review costs
- Update dependencies
- Review user feedback

**Quarterly:**
- Security audit
- Performance optimisation
- Feature requests evaluation

**Estimated ongoing time: 4-8 hours/month**

## Success metrics

**Usage:**
- Active users per day
- Total instances spawned per month
- Average session duration
- Return users

**Technical:**
- Uptime percentage
- Average container spawn time
- Resource utilization
- Cost per user

**Community:**
- GitHub stars
- Workshop adoptions
- User feedback
- Contributions

## What NOT to do

- ❌ Build a custom web UI for simulator (web terminal is enough)
- ❌ Add user accounts/authentication for MVP
- ❌ Optimise prematurely (works fine as-is)
- ❌ Deploy to multiple regions (single Hetzner server sufficient)
- ❌ Add payment/subscription (free service)
- ❌ Build mobile app
- ❌ Add fancy features nobody asked for

Focus on: Zero-friction access to working simulator.

## Launch checklist

- [ ] Dockerfile builds successfully
- [ ] All protocols work in container
- [ ] State reset works
- [ ] Web terminal works
- [ ] Container orchestration works
- [ ] Landing page deployed
- [ ] DNS configured
- [ ] SSL certificate working
- [ ] Monitoring in place
- [ ] Documentation written
- [ ] Load tested (10 concurrent users)
- [ ] Security reviewed
- [ ] Backup procedures documented
- [ ] Announced to community

## Estimated costs

**Development:**
- 3-4 weeks developer time

**Ongoing monthly:**
- Hetzner CX51: €30/month
- Domain: €1/month
- Backups: €5/month
- **Total: ~€35-40/month**

**Time:**
- Setup: 3-4 weeks
- Maintenance: 4-8 hours/month

## Alternative: Easier MVP

If 3-4 weeks is too much cost or timewise, a simpler version could be:

**Week 1: Basic Docker deployment**
- Containerise simulator
- Deploy to single Hetzner server
- Expose SSH access with web instructions
- Manual instance management
- No fancy web terminal

**Result:**
- Documentation says: "SSH to uu-pl.org, run attack scripts"
- Each user gets SSH account (created manually)
- Simpler but functional
- Can enhance with web terminal later

This gets us from zero to public service in 1 week instead of 4.
