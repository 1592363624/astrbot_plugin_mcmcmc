from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.platform import MessageType
from astrbot.api.event.filter import PlatformAdapterType
import asyncio
import aiohttp
import json

@register("minecraft_monitor", "YourName", "Minecraft服务器监控插件，定时获取服务器状态", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.task = None  # 用于存储定时任务
        
        # 从配置获取参数，不再使用具体的默认值
        self.target_group = self.config.get("target_group")
        self.server_name = self.config.get("server_name", "Minecraft服务器")
        self.server_ip = self.config.get("server_ip")
        self.server_port = self.config.get("server_port")
        self.check_interval = self.config.get("check_interval", 10)
        self.enable_auto_monitor = self.config.get("enable_auto_monitor", False)
        
        # 状态缓存，用于检测变化
        self.last_player_count = None  # 上次的玩家数量，None表示未初始化
        self.last_player_list = []     # 上次的玩家列表
        self.last_status = None        # 上次的服务器状态
        
        # 检查必要的配置是否完整
        if not self.target_group or not self.server_ip or not self.server_port:
            logger.error("Minecraft监控插件配置不完整，缺少 target_group、server_ip 或 server_port，自动监控功能将不会启动。")
            logger.error("请在配置文件中设置以下参数: target_group, server_ip, server_port")
            self.enable_auto_monitor = False
        else:
            # 确保 target_group 是字符串类型
            self.target_group = str(self.target_group)
            logger.info(f"Minecraft监控插件已加载 - 目标群: {self.target_group}, 服务器: {self.server_ip}:{self.server_port}")
        
        # 如果启用了自动监控且配置完整，延迟启动任务
        if self.enable_auto_monitor:
            asyncio.create_task(self._delayed_auto_start())
    
    async def _delayed_auto_start(self):
        """延迟自动启动监控任务"""
        await asyncio.sleep(5)  # 等待5秒让插件完全初始化
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.direct_hello_task())
            logger.info("🚀 自动启动服务器监控任务")
    
    async def get_hitokoto(self):
        """获取一言句子"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://v1.hitokoto.cn/?encode=text", timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        text = await response.text()
                        return text.strip()
                    else:
                        logger.warning(f"获取一言失败: HTTP {response.status}")
                        return None
        except aiohttp.ClientError as e:
            logger.warning(f"获取一言网络请求失败: {e}")
            return None
        except asyncio.TimeoutError:
            logger.warning("获取一言请求超时")
            return None
        except Exception as e:
            logger.warning(f"获取一言时发生未知错误: {e}")
            return None
    

    async def get_minecraft_server_info(self, format_message=True):
        """获取Minecraft服务器信息"""
        # 检查配置完整性
        if not self.server_ip or not self.server_port:
            error_msg = "服务器IP或端口未配置"
            logger.error(error_msg)
            return f"❌ {error_msg}" if format_message else None
        
        try:
            url = f"https://motd.minebbs.com/api/status?ip={self.server_ip}&port={self.server_port}&stype=je"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.info(f"API返回数据: {data}")  # 调试日志
                        except json.JSONDecodeError:
                            error_msg = f"API响应JSON解析失败: {await response.text()}"
                            logger.error(error_msg)
                            return f"❌ {error_msg}" if format_message else None
                        
                        # 根据实际API格式提取服务器信息
                        server_status = data.get('status', '未知')
                        
                        # 使用配置中的服务器名称，不再从API获取
                        server_name = self.server_name
                            
                        version = data.get('version', '未知版本')
                        
                        # 处理玩家信息
                        players_info = data.get('players', {})
                        if isinstance(players_info, dict):
                            online_players = players_info.get('online', 0)
                            max_players = players_info.get('max', 0)
                            player_sample = players_info.get('sample', [])
                        else:
                            online_players = 0
                            max_players = 0
                            player_sample = []
                        
                        # 如果不需要格式化消息，返回原始数据
                        if not format_message:
                            return {
                                'status': server_status,
                                'name': server_name,
                                'version': version,
                                'online': online_players,
                                'max': max_players,
                                'players': player_sample
                            }
                        
                        # 构建消息
                        status_emoji = "🟢" if server_status == "online" else "🔴"
                        message = f"{status_emoji} 服务器: {server_name}\n"
                        message += f"🎮 版本: {version}\n"
                        message += f"👥 在线玩家: {online_players}/{max_players}"
                        
                        # 处理玩家列表
                        if player_sample and isinstance(player_sample, list) and len(player_sample) > 0:
                            if isinstance(player_sample[0], dict):
                                player_names = [player.get('name', '未知玩家') for player in player_sample[:10]]
                            else:
                                player_names = [str(player) for player in player_sample[:10]]
                            message += f"\n📋 玩家列表: {', '.join(player_names)}"
                            if len(player_sample) > 10:
                                message += f" (+{len(player_sample) - 10}人)"
                        elif player_sample == "无" or online_players == 0:
                            message += "\n📋 当前无玩家在线"
                        else:
                            message += f"\n📋 玩家列表: {player_sample}"
                            
                        return message
                    else:
                        error_msg = f"获取服务器信息失败 (状态码: {response.status})"
                        logger.warning(error_msg)
                        return f"❌ {error_msg}" if format_message else None
                        
        except aiohttp.ClientError as e:
            error_msg = f"网络请求失败: {e}"
            logger.error(error_msg)
            return f"❌ {error_msg}" if format_message else None
        except asyncio.TimeoutError:
            error_msg = "请求超时"
            logger.warning(error_msg)
            return f"❌ {error_msg}" if format_message else None
        except Exception as e:
            error_msg = f"获取服务器信息时发生未知错误: {e}"
            logger.error(error_msg)
            return f"❌ {error_msg}" if format_message else None
    
    def check_server_changes(self, server_data):
        """检查服务器状态是否有变化，返回是否需要发送消息和变化描述"""
        if server_data is None:
            return False, "获取服务器数据失败"
        
        current_online = server_data['online']
        current_players = server_data['players']
        current_status = server_data['status']
        
        # 获取当前玩家名单（用于比较）
        if isinstance(current_players, list):
            current_player_names = []
            for player in current_players:
                if isinstance(player, dict):
                    current_player_names.append(player.get('name', ''))
                else:
                    current_player_names.append(str(player))
        else:
            current_player_names = []
        
        # 检查是否是首次检查（使用 None 判断）
        if self.last_player_count is None:
            # 首次检查，更新缓存但不发送消息（除非有玩家在线）
            self.last_player_count = current_online
            self.last_player_list = current_player_names.copy()
            self.last_status = current_status
            
            if current_online > 0:
                return True, "服务器监控已启动，当前有玩家在线"
            else:
                return True, "服务器监控已启动"
        
        # 检查变化
        changes = []
        
        # 检查服务器状态变化
            # 不推送服务器上下线变化，只推送玩家变化
        
        # 检查玩家数量变化
        player_diff = current_online - self.last_player_count
        if player_diff > 0:
            # 有玩家加入
            new_players = set(current_player_names) - set(self.last_player_list)
            if new_players:
                changes.append(f"📈 {', '.join(new_players)} 加入了服务器 (+{player_diff})")
            else:
                changes.append(f"📈 有 {player_diff} 名玩家加入了服务器")
        elif player_diff < 0:
            # 有玩家离开
            left_players = set(self.last_player_list) - set(current_player_names)
            if left_players:
                changes.append(f"📉 {', '.join(left_players)} 离开了服务器 ({player_diff})")
            else:
                changes.append(f"📉 有 {abs(player_diff)} 名玩家离开了服务器")
        
        # 更新缓存
        self.last_player_count = current_online
        self.last_player_list = current_player_names.copy()
        self.last_status = current_status
        
        # 如果有变化，返回True和变化描述
        if changes:
            return True, "\n".join(changes)
        else:
            return False, "无变化"
    async def initialize(self):
        """插件初始化方法"""
        logger.info("Minecraft服务器监控插件已加载，使用 /start_hello 启动定时任务")
    
    async def notify_subscribers(self, message: str):
        """发送通知到目标群组（抽象的通知函数）"""
        if not self.target_group:
            logger.error("❌ 目标群号未配置，无法发送通知")
            return False
        
        try:
            # 获取AIOCQHTTP客户端并发送
            platform = self.context.get_platform(PlatformAdapterType.AIOCQHTTP)
            
            if not platform or not hasattr(platform, 'get_client'):
                logger.error("❌ 无法获取AIOCQHTTP客户端")
                return False
                
            client = platform.get_client()
            
            result = await client.api.call_action('send_group_msg', **{
                'group_id': int(self.target_group),
                'message': message
            })
            
            if result and result.get('message_id'):
                logger.info(f"✅ 已发送通知到群 {self.target_group}")
                return True
            else:
                logger.warning(f"❌ 发送失败: {result}")
                return False
        except Exception as e:
            logger.error(f"发送通知时出错: {e}")
            return False
    
    async def direct_hello_task(self):
        """定时获取并检测Minecraft服务器变化"""
        while True:
            try:
                # 等待配置的检查间隔
                await asyncio.sleep(self.check_interval)
                
                # 获取服务器原始数据
                server_data = await self.get_minecraft_server_info(format_message=False)
                
                if server_data is None:
                    logger.warning("❌ 获取服务器数据失败，跳过本次检查")
                    continue
                
                # 检查是否有变化
                should_send, change_message = self.check_server_changes(server_data)
                
                if should_send:
                    # 有变化，发送消息
                    # 先发送变化提醒
                    change_notification = f"🔔 服务器状态变化：\n{change_message}"
                    
                    # 再发送完整的服务器状态
                    full_status = await self.get_minecraft_server_info(format_message=True)
                    
                    # 获取一言句子
                    hitokoto = await self.get_hitokoto()
                    
                    # 构建最终消息
                    final_message = f"{change_notification}\n\n📊 当前状态：\n{full_status}"
                    if hitokoto:
                        final_message += f"\n\n💬 {hitokoto}"
                    
                    # 使用抽象的通知函数发送消息
                    await self.notify_subscribers(final_message)
                else:
                    # 无变化，仅记录日志
                    logger.info(f"🔍 服务器状态无变化: 玩家数 {server_data['online']}/{server_data['max']}")
                    
            except Exception as e:
                logger.error(f"定时监控任务出错: {e}")
                # 出错时等待一下再继续
                await asyncio.sleep(5)

    # 基础指令
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """Hello World 指令"""
        user_name = event.get_sender_name()
        yield event.plain_result(f"Hello, {user_name}!")

    # 定时任务控制指令
    @filter.command("start_server_monitor")
    async def start_server_monitor_task(self, event: AstrMessageEvent):
        """启动服务器监控任务"""
        if self.task and not self.task.done():
            yield event.plain_result("服务器监控任务已经在运行中")
            return
        
        self.task = asyncio.create_task(self.direct_hello_task())
        logger.info("启动服务器监控任务")
        yield event.plain_result("✅ 服务器监控任务已启动，每10秒发送一次服务器状态")
    
    @filter.command("stop_server_monitor")
    async def stop_server_monitor_task(self, event: AstrMessageEvent):
        """停止服务器监控任务"""
        if self.task and not self.task.done():
            self.task.cancel()
            logger.info("停止服务器监控任务")
            yield event.plain_result("✅ 服务器监控任务已停止")
        else:
            yield event.plain_result("❌ 监控任务未在运行")
    
    @filter.command("查询")
    async def get_server_status(self, event: AstrMessageEvent):
        """立即获取服务器状态"""
        server_info = await self.get_minecraft_server_info()
        
        # 获取一言句子
        hitokoto = await self.get_hitokoto()
        if hitokoto:
            server_info += f"\n\n💬 {hitokoto}"
        
        yield event.plain_result(server_info)
    
    @filter.command("reset_monitor")
    async def reset_monitor(self, event: AstrMessageEvent):
        """重置监控状态缓存"""
        self.last_player_count = None
        self.last_player_list = []
        self.last_status = None
        logger.info("监控状态缓存已重置")
        yield event.plain_result("✅ 监控状态缓存已重置，下次检测将视为首次检测")
    
    # 保留旧指令以兼容（作为代理）
    @filter.command("start_hello")
    async def start_hello_task(self, event: AstrMessageEvent):
        """启动定时发送任务（兼容旧版）"""
        # 直接代理到新方法，正确处理异步生成器
        async for result in self.start_server_monitor_task(event):
            yield result
    
    @filter.command("stop_hello")
    async def stop_hello_task(self, event: AstrMessageEvent):
        """停止定时发送任务（兼容旧版）"""
        # 直接代理到新方法，正确处理异步生成器
        async for result in self.stop_server_monitor_task(event):
            yield result
    
    @filter.command("set_group")
    async def set_target_group(self, event: AstrMessageEvent, group_id: str):
        """设置目标群号"""
        self.target_group = group_id
        logger.info(f"设置目标群号为: {group_id}")
        yield event.plain_result(f"目标群号已设置为: {group_id}")

    # 测试指令
    @filter.command("test_send")
    async def test_send(self, event: AstrMessageEvent):
        """测试发送服务器信息到目标群"""
        try:
            # 获取服务器信息
            server_info = await self.get_minecraft_server_info()
            
            platform = self.context.get_platform(PlatformAdapterType.AIOCQHTTP)
            if not platform or not hasattr(platform, 'get_client'):
                yield event.plain_result("❌ 无法获取AIOCQHTTP平台")
                return
                
            client = platform.get_client()
            
            result = await client.api.call_action('send_group_msg', **{
                'group_id': int(self.target_group),
                'message': f"📋 测试发送:\n{server_info}"
            })
            
            if result and result.get('message_id'):
                yield event.plain_result(f"✅ 测试发送成功！消息ID: {result.get('message_id')}")
            else:
                yield event.plain_result(f"❌ 测试发送失败: {result}")
                
        except Exception as e:
            yield event.plain_result(f"测试发送出错: {e}")

    async def terminate(self):
        """插件销毁方法"""
        # 停止定时任务
        if self.task and not self.task.done():
            self.task.cancel()
            logger.info("定时发送任务已停止")