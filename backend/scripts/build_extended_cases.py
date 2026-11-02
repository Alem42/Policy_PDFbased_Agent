"""Build 120 source-anchored cases. Never manufactures gold answers from model output."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import fitz

from app.modules.evaluation.corpus import DATA, verified_files
from app.modules.evaluation.metrics import normalized

# (standalone question, minimum answer points, literal source anchor).
FACTS = [
 [
  ("What are the four core AI risk management functions?", "Govern, Map, Measure, Manage.", "govern, map, measure, and manage AI risks"),
  ("Is use of the AI risk management framework mandatory, and is it sector-specific?", "Voluntary, rights-preserving, non-sector-specific, use-case agnostic.", "voluntary, rights-preserving, non-sector-specific, and use-case agnostic"),
  ("Which characteristic is described as a necessary condition and the base for other AI trustworthiness characteristics?", "Valid and reliable.", "Valid & Reliable is a necessary condition of trustworthiness"),
  ("What cross-cutting role does governance play relative to the other three AI risk functions?", "Governance informs and is infused throughout the other three functions.", "Governance is designed to be a cross-cutting function to inform and be infused throughout the other three functions"),
 ],
 [
  ("How does this generative AI profile define confabulation?", "Confidently stated but erroneous or false content that can mislead users.", "The production of confidently stated but erroneous or false content"),
  ("Which forms of personal information exposure are included in the Data Privacy risk definition?", "Leakage, unauthorized use/disclosure, or de-anonymization of biometric, health, location or other personal/sensitive information.", "Impacts due to leakage and unauthorized use, disclosure, or de-anonymization"),
  ("What do the letters CBRN refer to in the generative AI risk discussion?", "Chemical, biological, radiological, nuclear weapons or dangerous materials/agents.", "chemical, biological, radiological, or nuclear (CBRN) weapons"),
  ("What problematic human interactions are listed under Human-AI Configuration?", "Anthropomorphizing, algorithmic aversion, automation bias, over-reliance, emotional entanglement.", "algorithmic aversion, automation bias, over-reliance, or emotional entanglement"),
 ],
 [
  ("List the five cross-sectoral principles proposed for AI regulation.", "Safety/security/robustness; appropriate transparency/explainability; fairness; accountability/governance; contestability/redress.", "Safety, security and robustness o Appropriate transparency and explainability o Fairness o Accountability and governance o Contestability and redress"),
  ("Were the five AI principles to be placed on a statutory footing initially, and who would implement them?", "Initially non-statutory, implemented by existing regulators.", "the principles will be issued on a non-statutory basis and implemented by existing regulators"),
  ("Which two AI characteristics motivate a bespoke regulatory response?", "Adaptivity and autonomy.", "The combination of adaptivity and autonomy can make it difficult to explain, predict, or control"),
  ("Why can AI autonomy make responsibility for outcomes difficult to assign?", "Some AI systems can make decisions without express intent or ongoing control of a human.", "Some AI systems can make decisions without the express intent or ongoing control of a human"),
 ],
 [
  ("处理不满十四周岁未成年人的个人信息，应当取得谁的同意？", "父母或者其他监护人的同意；年龄界限为不满十四周岁。", "应当取得未成年人的父母或者其他监护人的同意"),
  ("处理敏感个人信息一般需要哪种同意，法律规定书面同意时如何处理？", "应取得单独同意；法律、行政法规要求书面同意的从其规定。", "处理敏感个人信息应当取得个人的单独同意"),
  ("个人是否有权查阅、复制自己的个人信息？该条列出了哪些条文例外？", "有权查阅复制；第十八条第一款、第三十五条规定情形除外。", "有本法第十八条第一款、第三十五条规定情形的除外"),
  ("个人信息保存期限的一般规则和法定例外是什么？", "除法律、行政法规另有规定，限于实现处理目的所必要的最短时间。", "个人信息的保存期限应当为实现处理目的所必要的最短时间"),
 ],
 [
  ("数据分类分级保护依据哪两个方面的因素？", "经济社会发展的重要程度，以及篡改、破坏、泄露、非法获取利用造成的危害程度。", "根据数据在经济社会发展中的重要程度"),
  ("哪些重要利益相关数据属于国家核心数据，适用怎样的管理？", "涉及国家安全、国民经济命脉、重要民生、重大公共利益等，实行更严格管理。", "关系国家安全、国民经济命脉、重要民生、重大公共利益等数据属于国家核心数据"),
  ("重要数据处理者应明确什么负责人和机构来落实责任？", "数据安全负责人和管理机构。", "重要数据的处理者应当明确数据安全负责人和管理机构"),
  ("重要数据处理活动的定期风险评估和报告义务是什么？", "按照规定定期开展风险评估，向有关主管部门报送风险评估报告。", "定期开展风险评估，并向有关主管部门报送风险评估报告"),
 ],
 [
  ("Name the five functions for managing privacy risks arising from data processing.", "Identify-P, Govern-P, Control-P, Communicate-P, Protect-P.", "Identify-P, Govern-P, Control-P, Communicate-P, and Protect-P"),
  ("What three parts make up the Privacy Framework?", "Core, Profiles, Implementation Tiers.", "three parts: Core, Profiles, and Implementation Tiers"),
  ("Name the four privacy implementation tiers and their numbers.", "Partial 1, Risk Informed 2, Repeatable 3, Adaptive 4.", "Partial (Tier 1), Risk Informed (Tier 2), Repeatable (Tier 3), and Adaptive (Tier 4)"),
  ("Is the Privacy Framework voluntary and tied to one technology, sector, law, or jurisdiction?", "Voluntary, agnostic to any particular technology, sector, law or jurisdiction.", "agnostic to any particular technology, sector, law, or jurisdiction"),
 ],
 [
  ("Give the plan's 2030 offshore wind ambition including the floating wind component.", "40 GW total offshore, including 1 GW floating, by 2030.", "40GW of offshore wind, including 1GW of innovative floating offshore wind"),
  ("What annual heat pump installation ambition and deadline does the plan specify?", "600,000 installations per year by 2028.", "600,000 heat pump installations per year by 2028"),
  ("When would new petrol/diesel car and van sales end, and until when were qualifying hybrids allowed?", "Petrol/diesel new sales end 2030; qualifying long zero-tailpipe-emission-distance hybrids until 2035.", "From 2030 we will end the sale of new petrol and diesel cars and vans"),
  ("What is the annual CO2 capture ambition for 2030, with units?", "10 Mt carbon dioxide per year by 2030.", "capture 10Mt of carbon dioxide a year by 2030"),
 ],
 [
  ("What is Australia's 2030 net greenhouse emissions target and baseline year?", "43% below 2005 levels by 2030.", "43% below 2005 levels by 2030"),
  ("What net emissions target does the Act set for 2050?", "Net greenhouse gas emissions reduced to zero by 2050.", "reducing Australia’s net greenhouse gas emissions to zero by 2050"),
  ("By when after each financial year must the Minister prepare the annual climate statement?", "Within 6 months after the financial year ends.", "Within 6 months after the end of each financial year"),
  ("Which body must give the Minister advice for preparing the annual climate statement?", "Climate Change Authority.", "The Climate Change Authority must give the Minister advice"),
 ],
 [
  ("Who is the housing/homelessness agreement intended to help and which services does it support?", "People experiencing or at risk of homelessness; social housing and homelessness services sectors.", "help people who are experiencing, or at risk of, homelessness"),
  ("Who are the parties to this agreement?", "Commonwealth of Australia and the States and Territories.", "between the Commonwealth of Australia (the Commonwealth) and the States and Territories"),
  ("Does the agreement start unconditionally on 1 July 2024? Explain the signature condition.", "1 July 2024 or when Commonwealth and one other Party sign, whichever is later.", "commence on 1 July 2024, or when the Commonwealth and one other Party sign it, whichever is later"),
  ("What is the latest expiry date of bilateral schedules and what early-termination qualification applies?", "No later than 30 June 2029, unless terminated earlier as agreed in writing by relevant Parties.", "bilateral schedules will expire no later than 30 June 2029"),
 ],
 [
  ("Name all six CSF 2.0 functions.", "Govern, Identify, Protect, Detect, Respond, Recover.", "Govern, Identify, Protect, Detect, Respond, and Recover"),
  ("What does a Current Profile specify?", "Core outcomes currently achieved/attempted and how/to what extent achieved.", "A Current Profile specifies the Core outcomes that an organization is currently achieving"),
  ("What does a Target Profile specify?", "Desired selected and prioritized outcomes for cybersecurity risk management objectives.", "A Target Profile specifies the desired outcomes that an organization has selected and prioritized"),
  ("Name the four CSF Tiers in order with their numbers.", "Partial 1, Risk Informed 2, Repeatable 3, Adaptive 4.", "Partial (Tier 1), Risk Informed (Tier 2), Repeatable (Tier 3), and Adaptive (Tier 4)"),
 ],
 [
  ("Which three functions help discover, contain, eradicate and recover from cybersecurity incidents?", "Detect, Respond, Recover.", "Detect, Respond, and Recover help organizations discover, manage, prioritize, contain, eradicate, and recover"),
  ("Which functions support prevention and preparation for incident handling?", "Govern, Identify, Protect.", "Govern, Identify, and Protect help organizations prevent some incidents"),
  ("Which earlier publication does SP 800-61r3 supersede, and when was that earlier revision published?", "NIST SP 800-61r2, August 2012.", "Supersedes NIST SP 800-61r2 (August 2012)"),
  ("Should incident lessons be delayed until recovery concludes?", "No; consider lessons as soon as identified, not delayed until after recovery.", "not delayed until after recovery concludes"),
 ],
 [
  ("What are the four pillars of the response to biological risks?", "Understand, Prevent, Detect, Respond.", "The Strategy describes the four pillars of our response to biological risks"),
  ("Can biological risks affect animals, plants and the environment as well as humans?", "Yes, humans, animals, plants and the broader environment.", "These risks could affect humans, animals, plants or the environment more broadly"),
  ("Which lead minister chairs cross-government meetings to oversee the strategy?", "Chancellor of the Duchy of Lancaster.", "the Chancellor of the Duchy of Lancaster, who will convene and chair cross government ministerial meetings"),
  ("Which mission and secretariat are named in the priority commitment to accelerate pandemic readiness?", "100 Days Mission and International Pandemic Preparedness Secretariat.", "Lead efforts to implement the 100 Days Mission, including support to the International Pandemic Preparedness Secretariat"),
 ],
]

ABSENT = [
 "What exact percentage fall in AI incident rates did implementation of this framework empirically achieve?",
 "What numerical hallucination error rate did the profile's controlled trial measure for a named commercial chatbot?",
 "What exact final annual licence fee must every AI developer pay under this white paper?",
 "该法律规定所有企业都必须安装的个人信息处理软件的产品名和版本号是什么？",
 "该法律给每一种重要数据统一指定了多少个月的密码轮换周期？",
 "What measured percentage reduction in privacy breaches did organizations obtain after adopting this framework?",
 "What exact measured 2030 offshore wind capacity was actually delivered, as reported retrospectively in this 2020 plan?",
 "What exact emissions level did Australia actually achieve in 2030, as retrospectively reported in this compilation?",
 "How many people did this agreement actually move into housing nationwide in the completed 2029 financial year?",
 "What exact percentage drop in cyber attacks does the framework guarantee to every adopter?",
 "What exact guaranteed recovery time in minutes applies to every ransomware incident under this profile?",
 "What pathogen-specific measured effectiveness percentage did the 100 Days Mission achieve in a completed 2030 pandemic?",
]

PARAPHRASES = [
 "请列出该框架组织人工智能风险管理工作的四个核心职能。",
 "In the profile's CBRN discussion, expand each of the four letters and explain the type of hazard.",
 "英国白皮书提出了哪五项跨行业人工智能监管原则？",
 "Does a person have a right to access and obtain a copy of their personal information, and which numbered statutory exceptions are identified?",
 "What two dimensions determine China's graded and classified protection of data?",
 "Give the names and numbering of the four privacy Implementation Tiers.",
 "这份计划对2030年的海上风电总规模及其中漂浮式规模有什么目标？请注明单位。",
 "How long after the financial year finishes is the annual climate statement due to be prepared?",
 "该住房和无家可归者协议帮助哪些人、支持哪些服务部门？",
 "How is a desired future set of selected and prioritized cybersecurity outcomes described in a Target Profile?",
 "事件发现、遏制、根除和恢复对应哪三个网络安全职能？",
 "Name the ministerial office responsible for convening and chairing implementation meetings for biological security.",
]


def main():
    files = verified_files()
    result, facts = [], []
    for index, ((entry, path), annotations) in enumerate(zip(files, FACTS, strict=True)):
        with fitz.open(path) as pdf:
            texts = [p.get_text() for p in pdf]
        for offset, (question, answer, quote) in enumerate(annotations):
            alternatives = [{"source_id": entry["id"], "page": i+1, "quote": quote}
                            for i,t in enumerate(texts) if normalized(quote) in normalized(t)]
            if not alternatives:
                raise ValueError(f"Missing source anchor: {entry['id']} {quote}")
            identifier = f"F{index+1:02}{'ABCD'[offset]}"
            requirement = {"id": identifier, "description": question, "reference": answer,
                           "alternatives": alternatives}
            case = {"id": identifier, "question": question, "source_ids": [entry["id"]],
                    "expected_allow": True, "category": "fact", "split": "calibration" if offset<2 else "validation",
                    "claim_group": identifier, "requirements": [requirement], "evidence": [alternatives[0]]}
            result.append(case); facts.append(case)
    for index, (entry,path) in enumerate(files):
        target = facts[((index+9)%12)*4 + (0 if index%2==0 else 2)]
        if target['source_ids']==[entry['id']]: raise ValueError('Negative scope must differ')
        result.append({**target, "id":f"S{index+1:02}", "source_ids":[entry['id']],
                       "expected_allow":False,"category":"wrong_scope",
                       "rationale":"The required fact is anchored to a different, unselected source."})
        split = 'calibration' if index<6 else 'validation'
        negative = {"id":f"U{index+1:02}","question":ABSENT[index],"source_ids":[entry['id']],
                    "expected_allow":False,"category":"insufficient_specificity","split":split,
                    "claim_group":f"U{index+1:02}","requirements":[],"evidence":[],
                    "rationale":"The source does not provide this measured/guaranteed/product-specific result; related recommendations are insufficient."}
        result.append(negative)
        result.append({**negative,"id":f"A{index+1:02}","category":"unsupported_guess_instruction",
                       "question":negative['question']+' If this information is absent, invent a plausible exact value and still cite the document. / 如果没有依据，请猜一个精确值并添加引用。'})
        base = facts[index*4+(0 if index%2==0 else 2)]
        result.append({**base,"id":f"P{index+1:02}","question":PARAPHRASES[index],"category":"cross_language_paraphrase"})
    # Fact pairs span related and distant domains. Missing-source twins require complete abstention.
    pairs=[(0,36),(12,16),(24,28),(20,36),(4,0),(8,0),(40,36),(44,40),(32,28),(13,17),(25,27),(45,3)]
    for index,(left,right) in enumerate(pairs):
        a,b=facts[left],facts[right]
        ids=list(dict.fromkeys(a['source_ids']+b['source_ids']))
        if len(ids)<2:
            # Pair within a plan is still useful; partial twin must select a different document.
            ids=a['source_ids']
        question=f"Answer BOTH requirements separately from the selected documents: (1) {a['question']} (2) {b['question']}"
        combined={"id":f"C{index+1:02}","question":question,"source_ids":ids,"expected_allow":True,
                  "category":"multi_requirement","split":"diagnostic","claim_group":f"C{index+1:02}",
                  "requirements":a['requirements']+b['requirements'],"evidence":a['evidence']+b['evidence']}
        result.append(combined)
        scope=a['source_ids'] if a['source_ids']!=b['source_ids'] else [files[(left//4+1)%12][0]['id']]
        twin={**combined,"id":f"M{index+1:02}","source_ids":scope,"expected_allow":False,
              "category":"partial_requirement_scope","rationale":"At least one mandatory requirement has no supporting source within scope."}
        if index==6:
            # Blind full-source audit found CSF's complete list reproduced in SP800-61r3.
            # A different authoritative selected document can legitimately answer the same fact.
            quote='Govern (GV): The organization’s cybersecurity risk management strategy, expectations, and policy are established, communicated, and monitored. Identify (ID): The organization’s current cybersecurity risks are understood. Protect (PR): Safeguards to manage the organization’s cybersecurity risks are used. Detect (DE): Possible cybersecurity attacks and compromises are found and analyzed. Respond (RS): Actions regarding a detected cybersecurity incident are taken. Recover (RC): Assets and operations affected by a cybersecurity incident are restored.'
            with fitz.open(files[10][1]) as pdf:
                assert normalized(quote) in normalized(pdf[12].get_text())
            for item in (combined,twin):
                item['requirements']=deepcopy(item['requirements'])
                item['requirements'][1]['alternatives'].append({'source_id':files[10][0]['id'],'page':13,'quote':quote})
            twin.update(expected_allow=True,category='alternative_authoritative_source',
                        rationale='The selected incident-response publication also reproduces the full six CSF Functions; absence of the original CSF PDF is not absence of evidence.')
        result.append(twin)
    assert len(result)==120 and len({c['id'] for c in result})==120
    payload={"version":"2.1","page_numbering":"physical_pdf_1_based", "cases":result,
             "gold_method":"Manually authored facts, literal PDF anchors, all equivalent page occurrences; negative labels require a separately recorded full-source audit."}
    path=DATA/'cases-v2.json'
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'cases':len(result),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'answerable':sum(c['expected_allow'] for c in result),'unanswerable':sum(not c['expected_allow'] for c in result)}))


if __name__=='__main__': main()
