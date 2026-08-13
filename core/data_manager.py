import json
import os
import base64
import tempfile
from datetime import datetime
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _normalize_path(filepath: str) -> str:
    """规范化文件路径，处理 Android Content URI 等特殊路径"""
    if not filepath:
        return filepath
    
    # 处理 Android Content URI (content://)
    if filepath.startswith("content://"):
        # 在 Android 上，FilePicker 可能返回 content:// URI
        # 这里我们尝试提取文件名，保存到应用私有目录
        import urllib.parse
        parsed = urllib.parse.urlparse(filepath)
        # 从路径中提取文件名
        path_parts = parsed.path.split("/")
        filename = path_parts[-1] if path_parts else "backup.txt"
        # 返回原始路径，让调用者处理
        return filepath
    
    # 处理文件协议 (file://)
    if filepath.startswith("file://"):
        filepath = filepath[7:]
    
    # 规范化路径
    return os.path.normpath(filepath)


class DataManager:
    def __init__(self, data_file="accounts.json", password=None):
        self.data_file = data_file
        self.accounts = []
        # 默认密钥，如果没有提供密码则使用固定密钥（基础保护）
        self.key = self._derive_key(password) if password else None
        self.load_data()

    def _derive_key(self, password: str, salt=None) -> bytes:
        """从密码派生加密密钥"""
        if salt is None:
            salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt

    def _encrypt(self, data: str) -> bytes:
        """加密字符串数据"""
        if self.key is None:
            # 无密码时使用简单编码（仅基础混淆）
            return base64.b64encode(data.encode('utf-8'))
        f = Fernet(self.key[0] if isinstance(self.key, tuple) else self.key)
        return f.encrypt(data.encode('utf-8'))

    def _decrypt(self, data: bytes) -> str:
        """解密数据"""
        if self.key is None:
            # 无密码时尝试 base64 解码
            try:
                return base64.b64decode(data).decode('utf-8')
            except:
                return data.decode('utf-8')
        try:
            f = Fernet(self.key[0] if isinstance(self.key, tuple) else self.key)
            return f.decrypt(data).decode('utf-8')
        except Exception:
            # 解密失败，尝试作为明文读取（兼容旧数据）
            try:
                return data.decode('utf-8')
            except:
                return "{}"

    def load_data(self):
        """从文件加载账号数据"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'rb') as f:
                    encrypted_data = f.read()
                # 空文件处理
                if not encrypted_data:
                    self.accounts = []
                    return
                json_str = self._decrypt(encrypted_data)
                # 解密失败或空内容
                if not json_str or json_str.strip() == '':
                    self.accounts = []
                    return
                self.accounts = json.loads(json_str)
            except Exception as e:
                print(f"加载数据失败: {e}")
                self.accounts = []
        else:
            self.accounts = []

    def save_data(self):
        """保存账号数据到文件（加密）"""
        try:
            json_str = json.dumps(self.accounts, ensure_ascii=False, indent=2)
            encrypted_data = self._encrypt(json_str)
            target_dir = os.path.dirname(os.path.abspath(self.data_file))
            os.makedirs(target_dir, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(prefix="accounts_", suffix=".tmp", dir=target_dir)
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(encrypted_data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, self.data_file)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            return True
        except Exception as e:
            print(f"保存数据失败: {e}")
            return False

    def get_all_accounts(self):
        """获取所有账号"""
        return self.accounts

    def add_account(self, username, password="", remark=""):
        """添加新账号"""
        account = {
            "id": self._generate_id(),
            "username": username,
            "password": password or "",
            "remark": remark,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.accounts.append(account)
        self.save_data()
        return account

    def update_account(self, account_id, username=None, password=None, remark=None):
        """更新账号信息"""
        for account in self.accounts:
            if account["id"] == account_id:
                if username is not None:
                    account["username"] = username
                if password is not None:
                    account["password"] = password
                if remark is not None:
                    account["remark"] = remark
                account["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.save_data()
                return account
        return None

    def delete_account(self, account_id):
        """删除账号"""
        for i, account in enumerate(self.accounts):
            if account["id"] == account_id:
                del self.accounts[i]
                self.save_data()
                return True
        return False

    def get_account_by_id(self, account_id):
        """根据ID获取账号"""
        for account in self.accounts:
            if account["id"] == account_id:
                return account
        return None

    def _generate_id(self):
        """生成唯一ID"""
        if not self.accounts:
            return 1
        return max(a["id"] for a in self.accounts) + 1

    def get_stats(self):
        """获取统计数据"""
        total = len(self.accounts)
        recent = len([a for a in self.accounts if self._is_recent(a.get("created_at", ""))])
        return {
            "total_accounts": total,
            "recent_added": recent,
        }

    def _is_recent(self, date_str):
        """检查是否为最近7天添加"""
        try:
            from datetime import timedelta
            date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            return (datetime.now() - date).days <= 7
        except:
            return False

    def export_to_file(self, filepath: str, export_password: str = None) -> bool:
        """导出账号到加密文件"""
        try:
            # 规范化路径
            filepath = _normalize_path(filepath)
            
            if filepath.startswith("content://"):
                try:
                    from android.os import Environment
                    download_dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                    filepath = os.path.join(download_dir.getAbsolutePath(), "accounts_backup.txt")
                except ImportError:
                    filepath = os.path.join(os.path.expanduser('~'), "accounts_backup.txt")
            
            json_str = json.dumps(self.accounts, ensure_ascii=False, indent=2)
            
            if export_password:
                # 使用密码加密导出
                key, salt = self._derive_key(export_password)
                f = Fernet(key)
                encrypted = f.encrypt(json_str.encode('utf-8'))
                # 存储格式: salt + encrypted
                data = base64.b64encode(salt + encrypted).decode('utf-8')
            else:
                # 无密码，仅 base64 编码
                data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(data)
            return True
        except Exception as e:
            print(f"导出失败: {e}")
            return False

    def import_from_file(self, filepath: str, import_password: str = None, merge: bool = True) -> tuple[bool, int]:
        """从文件导入账号
        
        Args:
            filepath: 导入文件路径
            import_password: 导入文件密码（如有）
            merge: True=合并现有数据, False=覆盖现有数据
            
        Returns:
            (成功, 导入数量)
        """
        try:
            # 规范化路径
            filepath = _normalize_path(filepath)
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = f.read()
            
            decoded = base64.b64decode(data)
            
            if import_password:
                # 需要密码解密
                salt = decoded[:16]
                encrypted = decoded[16:]
                key, _ = self._derive_key(import_password, salt)
                f = Fernet(key)
                json_str = f.decrypt(encrypted).decode('utf-8')
            else:
                # 尝试作为明文或简单编码
                try:
                    json_str = decoded.decode('utf-8')
                except:
                    json_str = data
            
            imported_accounts = json.loads(json_str)
            
            if not isinstance(imported_accounts, list):
                return False, 0

            normalized_accounts = []
            for account in imported_accounts:
                if not isinstance(account, dict):
                    continue
                username = str(account.get("username", "")).strip()
                raw_password = account.get("password", "")
                password = "" if raw_password is None else str(raw_password)
                if not username:
                    continue
                normalized_accounts.append({
                    "id": account.get("id"),
                    "username": username,
                    "password": password,
                    "remark": str(account.get("remark", "")),
                    "created_at": account.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "updated_at": account.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })

            if not normalized_accounts:
                return False, 0
            
            if merge:
                existing_ids = {a.get("id") for a in self.accounts}
                next_id = max((i for i in existing_ids if isinstance(i, int)), default=0) + 1
                for acc in normalized_accounts:
                    if not isinstance(acc["id"], int) or acc["id"] in existing_ids:
                        acc["id"] = next_id
                        next_id += 1
                    existing_ids.add(acc["id"])
                    self.accounts.append(acc)
            else:
                used_ids = set()
                next_id = 1
                for acc in normalized_accounts:
                    if not isinstance(acc["id"], int) or acc["id"] in used_ids:
                        while next_id in used_ids:
                            next_id += 1
                        acc["id"] = next_id
                    used_ids.add(acc["id"])
                self.accounts = normalized_accounts
            
            if not self.save_data():
                return False, 0
            return True, len(normalized_accounts)
        except Exception as e:
            print(f"导入失败: {e}")
            return False, 0
