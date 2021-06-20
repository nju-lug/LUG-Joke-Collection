from sre_constants import REPEAT_ONE
import requests
import pathlib
import json
from dateutil import parser
from requests.api import head, patch
import os
import re
import copy
import sys

GH_TOKEN = os.environ.get("GH_TOKEN", "")
ROOT = pathlib.Path(__file__).parent.resolve()
IMG_DIR = "./img"

class Issue(object):
    img_url_pattern = {
        "gitlab": r"!\[.*\]\((/uploads/.*\..{3,4})\)", 
        "github": r"!\[.*\]\((.*\..{3,4})\)", 
        "gitee": None,
    }

    def __init__(self, type, data, repo_url):
        if type == "gitlab":
            data["body"] = data.get("description", "")

        self.type = type
        self.raw_data = data
        self.repo_url = repo_url

        self.title = data.get("title", "")
        self.labels = data.get("labels", "")
        self.created_at = data.get("created_at", "")
        self.updated_at = data.get("updated_at", "")
        self.body = data.get("body", "")
        self.resources = re.findall(Issue.img_url_pattern[self.type], self.body)

    def download_resources(self, img_dir: pathlib.Path):
        if not img_dir.exists():
            img_dir.mkdir()
        for suffix in self.resources:
            r = requests.get(self.repo_url+suffix)
            assert r.status_code == 200
            img_path = img_dir / suffix[1:]
            if not img_path.parent.exists():
                img_path.parent.mkdir(parents=True)
            if img_path.exists() and img_path.is_file():
                continue
            with open(img_path, "wb") as fp:
                fp.write(r.content)

    def convert_url(self):
        """
        由于github和gitlab对于处理issue中图片的方式不同，我们这里直接将github中的issue导向repo中已经存储的图片
        """
        if self.type == "gitlab":
            targets = [self.repo_url + suffix for suffix in self.resources]
            for i in range(len(self.resources)):
                new_body = self.body.replace(self.resources[i], targets[i])
                self.body = new_body
                self.raw_data["body"] = new_body
        elif self.type == "github":
            targets = [self.repo_url + "/raw/master/" + IMG_DIR + suffix for suffix in self.resources]
            for i in range(len(self.resources)):
                new_body = self.body.replace(self.resources[i], targets[i])
                self.body = new_body
                self.raw_data["body"] = new_body
        elif self.type == "gitee":
            raise NotImplementedError
        else:
            raise ValueError

    def to(self, new_type, new_repo_url):
        new_issue = copy.deepcopy(self)
        new_issue.type = new_type
        new_issue.repo_url = new_repo_url
        return new_issue
    

def fetch_issues(request_url, repo_url, type, headers=None):
    r = requests.get(request_url, headers=headers)
    assert r.status_code == 200
    issues = json.loads(r.text)
    issues = [Issue(type, issue_data, repo_url) for issue_data in issues]
    issues.sort(key=lambda x:parser.parse(x.created_at))
    return issues


def post_issues(post_url, repo_url, type, new_issues, force=False, headers=None):
    session = requests.session()
    r = session.get(post_url, headers=headers)
    assert r.status_code == 200
    old_issues = json.loads(r.text)
    old_issues = [Issue(type, issue_data, repo_url) for issue_data in old_issues]

    for new_issue in new_issues:
        flag = True
        for old_issue in old_issues:
            if old_issue.title == new_issue.title:
                if force or (
                    parser.parse(old_issue.updated_at) < parser.parse(new_issue.updated_at)
                ) :
                    new_issue.download_resources(ROOT/IMG_DIR)
                    new_issue = new_issue.to(type, repo_url)
                    new_issue.convert_url()
                    patch_dict = {key:value for (key, value) in new_issue.__dict__.items() if key in ("title", "body", "labels")}
                    r = session.patch(post_url+"/{}".format(old_issue.raw_data["number"]), json.dumps(patch_dict), headers=headers)
                    assert r.status_code == 200
                flag = False
                break
            
        if flag:
            new_issue.download_resources(ROOT/IMG_DIR)
            new_issue = new_issue.to(type, repo_url)
            new_issue.convert_url()
            post_dict = {key:value for (key, value) in new_issue.__dict__.items() if key in ("title", "body", "labels")}
            r = session.post(post_url, json.dumps(post_dict), headers=headers)
            assert r.status_code == 201


if __name__ == "__main__":
    headers = {'Authorization': 'token {}'.format(GH_TOKEN)}
    new_issues = fetch_issues(
        "https://git.nju.edu.cn/api/v4/projects/2412/issues", 
        "https://git.nju.edu.cn/nju-lug/lug-joke-collection", 
        "gitlab", 
        headers=None
        )
    post_issues(
        "https://api.github.com/repos/nju-lug/LUG-Joke-Collection/issues", 
        "https://github.com/nju-lug/LUG-Joke-Collection", 
        "github", 
        new_issues, 
        force=eval(sys.argv[1]), 
        headers=headers
    )
