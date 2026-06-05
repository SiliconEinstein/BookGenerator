"""
Claude服务模块

处理Claude命令行工具的调用和管理。
"""

import asyncio
import subprocess
import json
import uuid
import shlex
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional, List, Dict, Any
import logging

from ..utils.config import config
from ..utils.exceptions import ClaudeProcessError, ConfigurationError

logger = logging.getLogger(__name__)


class ClaudeProcessConfig:
    """Claude进程配置"""

    def __init__(
        self,
        working_dir: Optional[str] = None,
        session_id: Optional[str] = None,
        continue_session: bool = False,
        timeout: int = 300
    ):
        self.working_dir = working_dir or config.claude_working_dir
        self.session_id = session_id
        self.continue_session = continue_session
        self.timeout = timeout


class ClaudeProcess:
    """Claude命令行进程封装"""

    def __init__(self, process_config: ClaudeProcessConfig):
        self.config = process_config
        self.process: Optional[asyncio.subprocess.Process] = None
        self.is_running = False
        self.process_id = str(uuid.uuid4())
        self.created_at = datetime.now()
        self.claude_session_id: Optional[str] = None  # Claude 返回的真实会话ID
        self.claude_command_path: Optional[str] = None

    async def start(self) -> None:
        """初始化Claude进程配置（命令行模式不需要启动持久进程）"""
        try:
            # 验证工作目录
            if self.config.working_dir and not Path(self.config.working_dir).exists():
                raise ConfigurationError(
                    f"Claude working directory does not exist: {self.config.working_dir}",
                    "claude_working_dir"
                )

            # 验证Claude CLI是否可用
            claude_command_name = config.claude_command
            claude_command_path = shutil.which(claude_command_name)

            if not claude_command_path:
                raise ClaudeProcessError(f"Claude CLI命令未找到: {claude_command_name}")
            
            self.claude_command_path = claude_command_path

            test_command = [self.claude_command_path, "--version"]
            try:
                process = await asyncio.create_subprocess_exec(
                    *test_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                if process.returncode != 0:
                    raise ClaudeProcessError(f"Claude CLI不可用: {stderr.decode('utf-8')}")
            except FileNotFoundError:
                # This case should now be handled by shutil.which, but kept for safety
                raise ClaudeProcessError(f"Claude CLI命令未找到: {claude_command_name}")

            self.is_running = True
            logger.info(f"Claude CLI配置验证成功", extra={
                "process_id": self.process_id,
                "working_dir": self.config.working_dir,
                "claude_command": self.claude_command_path
            })

        except Exception as e:
            logger.error(f"Failed to initialize Claude CLI: {e}")
            raise ClaudeProcessError(f"Failed to initialize Claude CLI: {e}")

    async def send_message(self, message: str) -> AsyncIterator[str]:
        """使用命令行模式发送消息并获取响应（实时流式解析stream-json格式）"""
        try:
            # 构建命令行参数
            command = self._build_query_command(message)
            
            # 打印完整的Claude CLI命令
            print(f"🚀 Claude CLI命令: {' '.join(command)}")
            
            # 记录要执行的完整命令
            logger.info(f"🚀 开始执行Claude CLI命令: {' '.join(command)}", extra={
                "process_id": self.process_id,
                "message_length": len(message),
                "full_command": command
            })

            # 执行命令并获取输出
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.working_dir if self.config.working_dir else None
            )

            logger.info(f"📡 Claude CLI进程已启动，PID: {process.pid}", extra={
                "process_id": self.process_id,
                "claude_pid": process.pid
            })

            # 实时读取stdout流
            line_buffer = ""
            byte_buffer = b""  # 字节缓冲区，用于处理多字节UTF-8字符
            line_count = 0
            content_chunks = 0
            
            try:
                while True:
                    # 读取一个字节
                    chunk = await process.stdout.read(1)
                    if not chunk:
                        # 进程结束，处理剩余的字节缓冲区
                        if byte_buffer:
                            try:
                                remaining_text = byte_buffer.decode('utf-8')
                                line_buffer += remaining_text
                            except UnicodeDecodeError:
                                logger.warning(f"⚠️ 进程结束时发现无法解码的字节: {byte_buffer}")
                        break
                    
                    # 将字节添加到缓冲区
                    byte_buffer += chunk
                    
                    # 尝试解码缓冲区中的字节
                    try:
                        # 尝试解码整个缓冲区
                        decoded_text = byte_buffer.decode('utf-8')
                        # 解码成功，将文本添加到行缓冲区，清空字节缓冲区
                        line_buffer += decoded_text
                        byte_buffer = b""
                        
                        # 检查是否有完整的行
                        while '\n' in line_buffer:
                            line, line_buffer = line_buffer.split('\n', 1)
                            line_count += 1
                            
                            if not line.strip():
                                continue
                            
                            # 打印Claude CLI的原始输出
                            print(f"📥 Claude CLI原始输出 - 第{line_count}行: {line}")
                            
                            logger.debug(f"📥 接收到第{line_count}行数据: {line[:100]}{'...' if len(line) > 100 else ''}", extra={
                                "process_id": self.process_id,
                                "line_number": line_count,
                                "line_length": len(line)
                            })
                            
                            try:
                                json_data = json.loads(line)
                                
                                logger.debug(f"🔍 解析JSON成功: type={json_data.get('type')}, keys={list(json_data.keys())}", extra={
                                    "process_id": self.process_id
                                })
                                
                                # 提取会话ID（从任何包含session_id的JSON对象中）
                                if 'session_id' in json_data and not self.claude_session_id:
                                    self.claude_session_id = json_data['session_id']
                                    logger.info(f"🔑 提取到会话ID: {self.claude_session_id}", extra={
                                        "process_id": self.process_id,
                                        "session_id": self.claude_session_id
                                    })
                                
                                # 检查result类型的对象
                                if json_data.get('type') == 'result':
                                    logger.debug(f"🎯 发现result对象: {json_data}", extra={
                                        "process_id": self.process_id
                                    })
                                
                                # 处理assistant消息类型，提取并流式返回内容
                                if json_data.get('type') == 'assistant' and 'message' in json_data:
                                    message_data = json_data['message']
                                    
                                    if 'content' in message_data and isinstance(message_data['content'], list):
                                        for content_item in message_data['content']:
                                            # 处理文本内容
                                            if content_item.get('type') == 'text' and 'text' in content_item:
                                                text = content_item['text']
                                                if text.strip():  # 只处理非空文本
                                                    content_chunks += 1
                                                    yield text + "\n"
                                            
                                            # 处理工具调用
                                            elif content_item.get('type') == 'tool_use':
                                                tool_name = content_item.get('name', '')
                                                tool_input = content_item.get('input', {})
                                                tool_id = content_item.get('id', '')
                                                
                                                # 格式化工具调用信息
                                                if tool_name == "TodoWrite":
                                                    tool_call_info = self._format_todo_write_display(tool_input)
                                                else:
                                                    tool_call_info = "```\n🔧 工具调用: " + tool_name + "\n"
                                                    if tool_input:
                                                        tool_call_info += "📝 参数: " + json.dumps(tool_input, ensure_ascii=False, indent=2) + "\n"
                                                    tool_call_info += "```"
                                                
                                                content_chunks += 1
                                                yield tool_call_info + "\n"
                                
                                # 跳过result类型消息，避免与assistant消息内容重复
                                elif json_data.get('type') == 'result':
                                    logger.debug(f"🔄 跳过result消息，避免重复内容", extra={
                                        "process_id": self.process_id,
                                        "result_length": len(json_data.get('result', ''))
                                    })
                                    continue
                                
                                # 处理其他类型的消息
                                elif json_data.get('type') in ['thinking', 'tool_use']:
                                    msg_type = json_data.get('type')
                                    logger.debug(f"🔄 处理{msg_type}类型消息", extra={
                                        "process_id": self.process_id,
                                        "message_type": msg_type
                                    })
                                    
                            except json.JSONDecodeError as e:
                                logger.warning(f"⚠️ 无法解析JSON行: {line[:100]}{'...' if len(line) > 100 else ''}, 错误: {e}", extra={
                                    "process_id": self.process_id,
                                    "line_number": line_count
                                })
                                continue
                        
                    except UnicodeDecodeError:
                        # 解码失败，说明当前字节序列不完整，继续读取更多字节
                        # 但要防止缓冲区无限增长
                        if len(byte_buffer) > 4:  # UTF-8字符最多4字节
                            # 如果缓冲区太大，可能是真的有问题，记录警告并重置
                            logger.warning(f"⚠️ 字节缓冲区过大，可能存在编码问题: {byte_buffer}")
                            byte_buffer = b""
                        continue


            except Exception as e:
                logger.error(f"❌ 流式读取过程中出错: {e}", extra={
                    "process_id": self.process_id,
                    "lines_processed": line_count,
                    "content_chunks": content_chunks
                })
                raise

            # 等待进程完成并检查返回码
            await process.wait()
            
            if process.returncode != 0:
                stderr_output = await process.stderr.read()
                error_msg = stderr_output.decode('utf-8') if stderr_output else "Unknown error"
                logger.error(f"❌ Claude CLI命令执行失败: {error_msg}", extra={
                    "process_id": self.process_id,
                    "return_code": process.returncode
                })
                raise ClaudeProcessError(f"Claude CLI执行失败: {error_msg}")

            logger.info(f"✅ Claude CLI命令执行完成，共处理{line_count}行，输出{content_chunks}块内容", extra={
                "process_id": self.process_id,
                "total_lines": line_count,
                "total_chunks": content_chunks
            })

        except asyncio.CancelledError:
            logger.info(f"🛑 消息处理被取消", extra={"process_id": self.process_id})
            if 'process' in locals() and process.returncode is None:
                process.terminate()
                await process.wait()
            raise
        except Exception as e:
            logger.error(f"❌ 发送消息到Claude时出错: {e}", extra={
                "process_id": self.process_id
            })
            raise ClaudeProcessError(f"Error sending message to Claude: {e}")



    def _build_command(self) -> List[str]:
        """构建Claude交互式命令行（已废弃，保留用于兼容性）"""
        command = [config.claude_command]

        # 调试信息：显示配置的工作目录
        logger.info(f"构建CLI命令 - 配置的工作目录: {self.config.working_dir}", extra={
            "process_id": self.process_id,
            "config_working_dir": self.config.working_dir
        })

        # 添加工作目录
        if self.config.working_dir:
            command.extend(["--add-dir", self.config.working_dir])
            logger.info(f"添加工作目录参数: --add-dir {self.config.working_dir}", extra={
                "process_id": self.process_id
            })

        # 处理会话参数 - 使用-r参数复用会话
        if self.config.session_id:
            # 验证session_id是否为有效的UUID格式
            try:
                uuid.UUID(self.config.session_id)
                # 如果是有效UUID，使用-r参数复用会话
                command.extend(["-r", self.config.session_id])
                logger.info(f"添加会话恢复参数: -r {self.config.session_id}", extra={
                    "process_id": self.process_id
                })
            except ValueError:
                # 如果不是有效UUID，记录警告但不添加参数，让Claude创建新会话
                logger.warning(f"提供的session_id不是有效UUID，将创建新会话: {self.config.session_id}", extra={
                    "process_id": self.process_id
                })
        else:
            logger.info("未提供session_id，将创建新会话", extra={
                "process_id": self.process_id
            })

        logger.info(f"执行Claude CLI命令: {' '.join(command)}", extra={
            "process_id": self.process_id,
            "full_command": command,
            "command_string": ' '.join(command)
        })
        return command

    def _build_query_command(self, message: str) -> List[str]:
        """构建查询命令"""
        if not self.claude_command_path:
            raise ClaudeProcessError("Claude command path not initialized.")
        
        cmd = [
            self.claude_command_path,
            "--output-format", "stream-json",
            "--verbose",
            "--disallowedTools", "Bash,Edit,BashOutput,KillShell",
            "--allowedTools", "Read,Write,Glob,Grep,Task,Agent,Skill",
            "--permission-mode", "dontAsk"
        ]
        
        # 添加工作目录
        logger.info(f"🔍 working_dir检查: {self.config.working_dir}", extra={
            "process_id": self.process_id
        })
        if self.config.working_dir:
            cmd.extend(["--add-dir", self.config.working_dir])
            logger.info(f"✅ 已添加--add-dir参数: {self.config.working_dir}", extra={
                "process_id": self.process_id
            })
        else:
            logger.warning(f"⚠️ working_dir为空，未添加--add-dir参数", extra={
                "process_id": self.process_id
            })
        
        # 添加会话ID
        if self.config.session_id:
            cmd.extend(["-r", self.config.session_id])
        
        # 添加消息
        # 在Windows上，提示中的换行符会破坏命令。
        # 将换行符替换为空格，以确保传递完整的提示。
        processed_message = message
        if sys.platform == "win32":
            processed_message = message.replace('\n', '\\n')
        cmd.extend(["-p", processed_message])
        
        logger.info(f"🚀 构建的Claude命令: {' '.join(cmd)}", extra={
            "process_id": self.process_id
        })
        
        return cmd

    def _format_todo_write_display(self, tool_input: Dict[str, Any]) -> str:
        """格式化TodoWrite工具调用的显示信息"""
        todos = tool_input.get("todos", [])
        if not todos:
            return "```\n📋 创建空任务列表\n```"

        # 统计任务状态
        pending_count = sum(1 for todo in todos if todo.get("status") == "pending")
        in_progress_count = sum(1 for todo in todos if todo.get("status") == "in_progress")
        completed_count = sum(1 for todo in todos if todo.get("status") == "completed")

        # 确定操作类型
        if in_progress_count > 0:
            action = "更新任务列表"
        elif completed_count == len(todos):
            action = "完成任务列表"
        else:
            action = "创建任务列表"

        result = f"```\n📋 {action} (共 {len(todos)} 项任务"
        if completed_count > 0:
            result += f"，已完成 {completed_count} 项"
        if in_progress_count > 0:
            result += f"，进行中 {in_progress_count} 项"
        result += ")\n"

        # 添加任务概要（使用无序号缩进格式）
        for todo in todos:
            status = todo.get("status", "pending")
            content = todo.get("content", "")
            active_form = todo.get("activeForm", "")

            status_emoji = {
                "pending": "⏳",
                "in_progress": "🔄",
                "completed": "✅"
            }.get(status, "📝")

            # 使用activeForm作为显示内容（如果存在且不为空）
            display_content = active_form if active_form and active_form.strip() else content

            result += f"  {status_emoji} {display_content}\n"

        result += "```"
        return result

    async def stop(self) -> None:
        """停止Claude进程（命令行模式下只需要标记为停止）"""
        if self.is_running:
            self.is_running = False
            logger.info(f"Claude CLI session stopped", extra={
                "process_id": self.process_id
            })

    def get_claude_session_id(self) -> Optional[str]:
        """获取Claude返回的真实会话ID"""
        return self.claude_session_id

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop()


class ClaudeService:
    """Claude服务管理器"""

    def __init__(self):
        self.active_processes: Dict[str, ClaudeProcess] = {}
        # 新增：基于session_id的进程缓存
        self.session_processes: Dict[str, ClaudeProcess] = {}

    async def get_or_create_process(
        self,
        session_id: Optional[str] = None,
        working_dir: Optional[str] = None,
        continue_session: bool = False
    ) -> ClaudeProcess:
        """获取或创建Claude进程，支持基于session_id的进程重用"""
        
        # 如果有session_id，尝试重用现有进程
        if session_id and session_id in self.session_processes:
            existing_process = self.session_processes[session_id]
            if existing_process.is_running:
                logger.info(f"重用现有Claude进程", extra={
                    "session_id": session_id,
                    "process_id": existing_process.process_id
                })
                return existing_process
            else:
                # 进程已停止，从缓存中移除
                logger.info(f"移除已停止的进程", extra={
                    "session_id": session_id,
                    "process_id": existing_process.process_id
                })
                del self.session_processes[session_id]
                if existing_process.process_id in self.active_processes:
                    del self.active_processes[existing_process.process_id]

        # 创建新进程
        process_config = ClaudeProcessConfig(
            working_dir=working_dir,
            session_id=session_id,
            continue_session=continue_session
        )

        process = ClaudeProcess(process_config)
        await process.start()

        self.active_processes[process.process_id] = process
        
        # 如果有session_id，缓存进程
        if session_id:
            self.session_processes[session_id] = process
            logger.info(f"缓存新的Claude进程", extra={
                "session_id": session_id,
                "process_id": process.process_id
            })

        return process

    async def create_process(
        self,
        session_id: Optional[str] = None,
        working_dir: Optional[str] = None,
        continue_session: bool = False
    ) -> ClaudeProcess:
        """创建新的Claude进程（保持向后兼容）"""
        return await self.get_or_create_process(session_id, working_dir, continue_session)

    def get_process(self, process_id: str) -> Optional[ClaudeProcess]:
        """获取活跃的Claude进程"""
        return self.active_processes.get(process_id)

    def get_process_by_session(self, session_id: str) -> Optional[ClaudeProcess]:
        """根据session_id获取进程"""
        return self.session_processes.get(session_id)

    async def remove_process(self, process_id: str) -> None:
        """移除并停止Claude进程"""
        if process_id in self.active_processes:
            process = self.active_processes.pop(process_id)
            
            # 从session缓存中移除
            session_id_to_remove = None
            for sid, cached_process in self.session_processes.items():
                if cached_process.process_id == process_id:
                    session_id_to_remove = sid
                    break
            
            if session_id_to_remove:
                del self.session_processes[session_id_to_remove]
                logger.info(f"从session缓存中移除进程", extra={
                    "session_id": session_id_to_remove,
                    "process_id": process_id
                })
            
            await process.stop()

    async def remove_session_process(self, session_id: str) -> None:
        """移除特定session的进程"""
        if session_id in self.session_processes:
            process = self.session_processes.pop(session_id)
            if process.process_id in self.active_processes:
                del self.active_processes[process.process_id]
            await process.stop()
            logger.info(f"移除session进程", extra={
                "session_id": session_id,
                "process_id": process.process_id
            })

    async def cleanup_all_processes(self) -> None:
        """清理所有活跃进程"""
        for process_id in list(self.active_processes.keys()):
            await self.remove_process(process_id)
        self.session_processes.clear()

    def get_active_process_count(self) -> int:
        """获取活跃进程数量"""
        return len(self.active_processes)

    def get_session_process_count(self) -> int:
        """获取缓存的session进程数量"""
        return len(self.session_processes)


# 全局Claude服务实例
_claude_service: Optional[ClaudeService] = None


def get_claude_service() -> ClaudeService:
    """获取全局Claude服务实例"""
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeService()
    return _claude_service