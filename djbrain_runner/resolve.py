"""Trusted allowlist resolver for DJ Brain: never execute user-supplied code."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path

REPOSITORY="volkovitskiyartem-lab/void-vibe-router"
ENTRYPOINT="djbrain_runner.execute"
REQUIRED={"repository","commit_sha","mode","seeds","entrypoint"}
OUTPUT_KEYS=("private_repo","private_sha","experiment_id","mode")

def resolve_experiment(experiment_id:str,registry_path:Path)->dict:
    if not isinstance(experiment_id,str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,39}",experiment_id):
        raise ValueError("Invalid experiment ID")
    data=json.loads(Path(registry_path).read_text(encoding="utf-8"))
    if not isinstance(data,dict) or set(data)!={"schema","experiments"} or data["schema"]!=1 or not isinstance(data["experiments"],dict):
        raise ValueError("Unsupported trusted registry")
    exp=data["experiments"].get(experiment_id)
    if not isinstance(exp,dict) or set(exp)!=REQUIRED:
        raise ValueError("Experiment not explicitly allowlisted")
    if exp["repository"]!=REPOSITORY or exp["entrypoint"]!=ENTRYPOINT:
        raise ValueError("Untrusted source/entrypoint")
    sha=exp["commit_sha"]
    if not isinstance(sha,str) or not re.fullmatch(r"[a-f0-9]{40}",sha):
        raise ValueError("Unreviewed or mutable SHA")
    mode=exp["mode"];seeds=exp["seeds"]
    if mode=="fixed":
        if seeds!=[36,37,38]:raise ValueError("Fixed sample must use original seeds")
    elif mode=="fresh":
        if (not isinstance(seeds,list) or not 1<=len(seeds)<=4 or
            any(type(x) is not int or x<=38 for x in seeds) or len(set(seeds))!=len(seeds)):
            raise ValueError("Invalid fresh seeds")
    else:raise ValueError("Unapproved experiment mode")
    return {"experiment_id":experiment_id,"repository":REPOSITORY,
            "commit_sha":sha,"mode":mode,"seeds":seeds,"entrypoint":ENTRYPOINT}

def write_github_outputs(experiment:dict,output_path:Path)->None:
    if set(experiment)!={"experiment_id","repository","commit_sha","mode","seeds","entrypoint"}:
        raise ValueError("Unexpected resolver output")
    if experiment["repository"]!=REPOSITORY or experiment["entrypoint"]!=ENTRYPOINT:
        raise ValueError("Tampered resolver output")
    if (not re.fullmatch(r"[a-f0-9]{40}",experiment["commit_sha"]) or
        not re.fullmatch(r"[a-z][a-z0-9-]{2,39}",experiment["experiment_id"])):
        raise ValueError("Invalid output value")
    values={"private_repo":REPOSITORY,"private_sha":experiment["commit_sha"],
            "experiment_id":experiment["experiment_id"],"mode":experiment["mode"]}
    with Path(output_path).open("a",encoding="utf-8") as out:
        for name in OUTPUT_KEYS:out.write(f"{name}={values[name]}\n")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--experiment-id",required=True)
    parser.add_argument("--registry",default=str(Path(__file__).with_name("approved_experiments.json")))
    parser.add_argument("--github-output",required=True)
    args=parser.parse_args()
    resolved=resolve_experiment(args.experiment_id,Path(args.registry))
    write_github_outputs(resolved,Path(args.github_output))
    print("Approved immutable DJ experiment selected; metadata withheld")

if __name__=="__main__":main()
