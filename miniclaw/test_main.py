import json
import unittest

from miniclaw.main import (
    MiniClawEngine,
    ensure_seed_files,
)


class MiniClawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_seed_files()

    def setUp(self):
        self.engine = MiniClawEngine()
        # 避免测试间互相干扰
        data = self.engine.skill_store.load()
        data["skills"] = [s for s in data.get("skills", []) if s.get("source") == "built-in"]
        self.engine.skill_store.save(data)

    def tearDown(self):
        self.engine.scheduler.stop()
        self.engine.wechat.stop()

    def test_dangerous_command_blocked(self):
        res = self.engine.executor.run("rm -rf /")
        self.assertFalse(res.get("ok", True))
        self.assertIn("危险命令", res.get("error", ""))

    def test_add_skill_internal_command(self):
        msg = self.engine._handle_internal_command("add_skill demo|说明|demo|fn|触发词")
        self.assertIn("能力已写入", msg)
        skills = self.engine.skill_store.load().get("skills", [])
        self.assertTrue(any(s.get("name") == "demo" for s in skills))

    def test_clock_crud_commands(self):
        msg = self.engine._handle_internal_command("clock add 巡检|9|echo ok")
        self.assertIn("定时任务已创建", msg)
        task_id = msg.split(":", 1)[1].strip()
        ls = self.engine._handle_internal_command("clock list")
        self.assertIn(task_id, ls)
        dis = self.engine._handle_internal_command(f"clock disable {task_id}")
        self.assertIn("禁用", dis)
        dele = self.engine._handle_internal_command(f"clock del {task_id}")
        self.assertIn("删除", dele)

    def test_help_contains_command_catalog(self):
        help_text = self.engine.show_help()
        data = json.loads(help_text)
        self.assertIn("commands", data)
        self.assertIn("help", data["commands"])


if __name__ == "__main__":
    unittest.main()
