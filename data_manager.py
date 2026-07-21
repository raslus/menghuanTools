import json
import os
from datetime import datetime


class DataManager:
    def __init__(self, data_file="accounts.json"):
        self.data_file = data_file
        self.accounts = []
        self.load_data()

    def load_data(self):
        """从文件加载账号数据"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.accounts = json.load(f)
            except Exception as e:
                print(f"加载数据失败: {e}")
                self.accounts = []
        else:
            self.accounts = []

    def save_data(self):
        """保存账号数据到文件"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.accounts, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存数据失败: {e}")
            return False

    def get_all_accounts(self):
        """获取所有账号"""
        return self.accounts

    def add_account(self, username, password, remark=""):
        """添加新账号"""
        account = {
            "id": self._generate_id(),
            "username": username,
            "password": password,
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
