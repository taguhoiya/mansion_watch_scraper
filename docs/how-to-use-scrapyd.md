To use **Scrapyd** with your project `mansion_watch_scraper` and its spider of the same name (`mansion_watch_scraper`), follow these steps:

---

### **1. Install Scrapyd and Required Tools**

Ensure that Scrapyd and the Scrapyd client are installed in your environment:

```bash
pip install scrapyd scrapyd-client
```

---

### **2. Start the Scrapyd Service**

Run Scrapyd to start the service. By default, it will listen on `http://localhost:6800`:

```bash
scrapyd
```

You should see logs indicating that Scrapyd is running. You can verify it by opening [http://localhost:6800](http://localhost:6800) in your browser.

---

### **3. Prepare Your Scrapy Project for Scrapyd**

Navigate to your Scrapy project directory (`mansion_watch_scraper`) and make sure it has a proper `scrapy.cfg` file. A basic `scrapy.cfg` looks like this:

```ini
[settings]
default = mansion_watch_scraper.settings

[deploy]
url = http://localhost:6800/
project = mansion_watch_scraper
```

---

### **4. Deploy Your Scrapy Project**

Deploy the project to Scrapyd using the `scrapyd-deploy` command:

1. Navigate to the root of your project.
2. Run the deploy command:
   ```bash
   scrapyd-deploy
   ```

This will upload your Scrapy project to Scrapyd, making it available for execution.

---

### **5. Schedule Your Spider**

Once the project is deployed, you can schedule the `mansion_watch_scraper` spider using the Scrapyd API:

```bash
curl http://localhost:6800/schedule.json -d project=mansion_watch_scraper -d spider=mansion_watch_scraper
```

This command sends an HTTP POST request to Scrapyd to start the spider. If successful, you’ll receive a response like this:

```json
{
  "node_name": "your-machine-name",
  "status": "ok",
  "jobid": "12345678-abcd-1234-efgh-1234567890ab"
}
```

---

### **6. Monitor Your Jobs**

Use the Scrapyd API to check the status of your jobs:

- **List all jobs** (pending, running, finished):

  ```bash
  curl http://localhost:6800/listjobs.json?project=mansion_watch_scraper
  ```

- **Cancel a running job**:
  ```bash
  curl http://localhost:6800/cancel.json -d project=mansion_watch_scraper -d job=12345678-abcd-1234-efgh-1234567890ab
  ```

---

### **7. Make Scrapyd Accessible Publicly**

If you need Scrapyd to accept requests from external sources:

1. **Edit the Scrapyd Config**:
   Locate the Scrapyd configuration file (e.g., `/etc/scrapyd/scrapyd.conf` or `~/.scrapyd.conf`) and update the `bind_address` to `0.0.0.0`:

   ```ini
   [scrapyd]
   bind_address = 0.0.0.0
   ```

2. **Restart Scrapyd**:
   Restart Scrapyd to apply the changes:

   ```bash
   scrapyd
   ```

3. **Open the Port**:
   - On your server, ensure the port (`6800` by default) is open and accessible to the public.
   - For a cloud server, configure the firewall or security group to allow inbound traffic on port `6800`.

---

### **8. Optional: Secure Your Scrapyd API**

Since Scrapyd doesn't come with built-in authentication, it's a good idea to secure access using methods like:

- **Reverse Proxy with Nginx/Apache**: Add basic authentication or use HTTPS.
- **Firewall Rules**: Restrict access to specific IPs.
- **Custom Scrapyd Deployments**: Implement middleware to check tokens or API keys.

---

### Example Workflow Summary

- Project Name: `mansion_watch_scraper`
- Spider Name: `mansion_watch_scraper`
- Schedule the spider:
  ```bash
  curl http://localhost:6800/schedule.json -d project=mansion_watch_scraper -d spider=mansion_watch_scraper
  ```
- Monitor jobs:
  ```bash
  curl http://localhost:6800/listjobs.json?project=mansion_watch_scraper
  ```
