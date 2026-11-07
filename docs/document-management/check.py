from pathlib import Path
import json,re,hashlib,urllib.parse,datetime
r=Path(__file__).resolve().parents[2];o=Path(__file__).resolve().parent
reg=json.loads((o/"registry.json").read_text(encoding="utf-8"));problems=[];warnings=[];count=0
for p in o.glob("*.md"):
 t=p.read_text(encoding="utf-8")
 for dest in re.findall(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)",t):
  dest=dest.strip("<>")
  if re.match(r"^[a-zA-Z][\w+.-]*:",dest) or dest.startswith("#"):continue
  count+=1;q=(p.parent/urllib.parse.unquote(dest.split("#")[0])).resolve()
  if not q.exists():problems.append({"source":p.name,"missing":dest})
active=[x for x in reg["documents"] if not x.get("removed")]
archived=[x["path"] for x in reg["documents"] if x.get("removed")]
for x in active:
 p=r/x["path"]
 if not p.exists():problems.append({"missing_registered_document":x["path"]})
 elif hashlib.sha256(p.read_bytes()).hexdigest()!=x["version"]["sha256"]:warnings.append({"changed_since_registration":x["path"],"note":x["version"].get("note","需复核变更")})
covered={x["path"] for x in active}
missing=[p.relative_to(r).as_posix() for d in ["docs","research"] for p in (r/d).rglob("*") if p.is_file() and p.suffix in [".md",".rst",".txt"] and o not in p.parents and p.relative_to(r).as_posix() not in covered and not (p.name=="summary.md" and p.parent.parent.name=="runs")]
result={"checked_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"registered_documents":len(covered),"archived_documents":archived,"new_local_links_checked":count,"new_link_failures":len([x for x in problems if "missing" in x]),"unregistered_documents":missing,"problems":problems,"content_drift_warnings":warnings,"scope":"新增Markdown目标存在、登记正文SHA256（removed项跳过并按历史保留）、docs/research文档覆盖（research/*/runs/*/summary.md 视为自动生成运行产物，按目录口径不逐次登记）、未验证锚点与外链"}
(o/"verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,ensure_ascii=False));raise SystemExit(1 if problems or missing else 0)
