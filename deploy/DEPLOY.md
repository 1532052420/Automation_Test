# 服务器部署指南（团队使用）

把框架部署到一台服务器，组员通过浏览器使用**测试平台**与**元素定位器**，无需每人配本地环境。

## 一、先想清楚的三件事（决定部署形态）

| 问题 | 说明 |
| --- | --- |
| 服务器能不能跑 APP 用例？ | **不能没有真机**。Appium 需要 USB 连接的 Android 手机插在服务器上；无真机的服务器只能跑**接口用例**与平台的管理/报告/调试能力 |
| 组员怎么提交用例和元素？ | 两条路：① 用例管理网页上传（本方案内置，上传即生效）；② 走 git 提交后在平台所在服务器 `git pull`。**推荐 git 为主、上传为辅**——上传的文件在服务器本地，git 管理会变脏 |
| 谁都能改能删吗？ | 用例管理支持访问口令（`ADMIN_TOKEN`）+ nginx basic auth；执行平台当前**同一时刻只允许 1 个执行任务**（单任务互斥），多人同时点开始会提示等待 |

## 二、部署步骤（Ubuntu 20.04+/Debian）

```bash
# 1. 上传代码到服务器（git clone 或 scp 整个目录）
git clone https://github.com/1532052420/AutomationTest-1.git /opt/AutomationTest

# 2. 一键初始化（python venv、依赖、allure、JDK8、adb、systemd 服务）
sudo bash /opt/AutomationTest/deploy/install_server.sh

# 3.（可选）服务器要接真机跑 APP 用例时
sudo bash /opt/AutomationTest/deploy/install_server.sh --with-appium
#    然后 USB 插手机、adb devices 授权

# 4. 设置用例管理口令（团队部署必做）
sudo systemctl edit automation-platform   # 覆写:
#   [Service]
#   Environment=ADMIN_TOKEN=换成随机口令
sudo systemctl restart automation-platform

# 5. 配置 nginx 反代（团队入口）
sudo apt install -y nginx
sudo cp /opt/AutomationTest/deploy/nginx-automation.conf /etc/nginx/sites-available/automation
sudo ln -sf /etc/nginx/sites-available/automation /etc/nginx/sites-enabled/
sudo nginx -t && sudo nginx -s reload
```

完成后组员访问：`http://<服务器IP>/`（测试平台）、`http://<服务器IP>/locator/`（元素定位器）。

## 三、日常运维

```bash
systemctl status automation-platform element-locator   # 服务状态
sudo systemctl restart automation-platform             # 改了框架代码后重启生效
tail -f /opt/AutomationTest/logs/platform.log          # 平台日志
journalctl -u element-locator -f                       # 定位器日志
```

代码更新：`cd /opt/AutomationTest && git pull && sudo systemctl restart automation-platform`

## 四、部署到公网前的安全清单（必做）

1. `ADMIN_TOKEN` 已修改为强随机值（用例管理上传/删除的口令）
2. nginx basic auth 已启用（平台整体访问口令），或平台仅在内网/VPN 暴露
3. 云服务器安全组：仅放行 80（nginx）与 SSH，**不要**直接放行 8080/8001/4726
4. 报告静态服务端口（4000 起随机端口）仅内网分享；公网使用建议改走 nginx 或加防火墙限制

## 五、已知限制（当前版本）

- 执行平台同一时刻仅 1 个执行任务（第 2 个人点开始会提示"已有任务正在运行"）
- 元素定位器同一时刻适合 1 人抓元素（会话态）
- 服务器无真机时，执行页/定位器的设备相关功能不可用，其余（接口用例执行、用例管理、报告）正常
- 用例里如有 `requests` 外网依赖，服务器需能访问对应被测环境

## 六、需要你提供/决定的事项

1. 服务器：IP、操作系统版本（当前脚本适配 Ubuntu/Debian）、SSH 访问方式
2. 部署位置：内网 / 公网？（决定安全策略强度）
3. APP 用例方案：服务器接真机？还是先只跑接口用例？
4. 团队口令：`ADMIN_TOKEN` 与 nginx basic auth 的账号密码
5. 用例提交约定：用例管理上传为主，还是 git 提交为主
