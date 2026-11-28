"""Policy-driven full-and-final settlement component calculator.

No statutory rates, eligibility thresholds or jurisdiction rules are embedded.
An approved effective-dated policy is required before automatic calculation.
"""
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
CENT=Decimal("0.01")
def money(value): return Decimal(str(value)).quantize(CENT,rounding=ROUND_HALF_UP)
def validate_exit_policy(config):
    if not isinstance(config,dict): raise HTTPException(422,"Exit statutory policy configuration must be an object")
    basis=config.get("daily_wage_basis")
    if basis not in {"basic","gross"}: raise HTTPException(422,"Policy daily_wage_basis must be basic or gross")
    try: divisor=Decimal(str(config["working_days_divisor"]))
    except Exception as exc: raise HTTPException(422,"Policy working_days_divisor is required and numeric") from exc
    if divisor<=0 or divisor>31: raise HTTPException(422,"Policy working_days_divisor must be between 0 and 31")
    for key in ("gratuity","leave_encashment","notice_pay"):
        rule=config.get(key,{})
        if not isinstance(rule,dict) or not isinstance(rule.get("enabled",False),bool):
            raise HTTPException(422,f"Policy {key} rule must be an object with enabled boolean")
        if rule.get("enabled"):
            for field in (("minimum_service_years","days_per_service_year","divisor") if key=="gratuity" else
                          ("divisor",) if key=="leave_encashment" else ("treatment",)):
                if field not in rule: raise HTTPException(422,f"Enabled {key} policy requires {field}")
            if key=="notice_pay" and rule["treatment"] not in {"earning","deduction"}:
                raise HTTPException(422,"Notice pay treatment must be earning or deduction")
    rounding=config.get("service_year_rounding","completed")
    if rounding not in {"completed","round_up_after_half","fractional"}:
        raise HTTPException(422,"service_year_rounding must be completed, round_up_after_half or fractional")
    if config.get("leave_encashment",{}).get("wage_basis","basic") not in {"basic","gross"}:
        raise HTTPException(422,"Leave encashment wage_basis must be basic or gross")
    deductions=config.get("statutory_deductions",[])
    if not isinstance(deductions,list): raise HTTPException(422,"statutory_deductions must be a list")
    for item in deductions:
        if not isinstance(item,dict) or not str(item.get("name","")).strip():
            raise HTTPException(422,"Each statutory deduction requires a name")
        try: rate=Decimal(str(item.get("rate_percent",0))); fixed=Decimal(str(item.get("fixed_amount",0)))
        except Exception as exc: raise HTTPException(422,"Statutory deduction rates and fixed amounts must be numeric") from exc
        if rate<0 or rate>100 or fixed<0: raise HTTPException(422,"Statutory deduction values are outside allowed ranges")
        if item.get("basis","gross") not in {"gross","gratuity","leave_encashment","notice_pay"}:
            raise HTTPException(422,"Unsupported statutory deduction basis")
    return config

def calculate_exit_settlement(*,config,monthly_basic,monthly_gross,service_years,leave_balances,loan_balances,notice_days_unserved,additional_earnings=None):
    config=validate_exit_policy(config)
    wage=Decimal(str(monthly_basic if config["daily_wage_basis"]=="basic" else monthly_gross))
    daily=wage/Decimal(str(config["working_days_divisor"]))
    earnings=[]; deductions=[]
    for item in additional_earnings or []:
        if not isinstance(item,dict) or len(str(item.get("type","")).strip())<2:
            raise HTTPException(422,"Every additional settlement earning requires a type")
        try: amount=money(item.get("amount"))
        except Exception as exc: raise HTTPException(422,"Additional settlement earnings must have numeric amounts") from exc
        if amount<=0: raise HTTPException(422,"Additional settlement earnings must be greater than zero")
        earnings.append({"type":str(item["type"]).strip(),"amount":str(amount),"source":"manager-supplied payroll component"})
    gratuity=config.get("gratuity",{})
    years=Decimal(str(service_years))
    if config.get("service_year_rounding","completed")=="completed":
        years=years.to_integral_value(rounding="ROUND_FLOOR")
    elif config.get("service_year_rounding")=="round_up_after_half":
        whole=years.to_integral_value(rounding="ROUND_FLOOR")
        years=whole+(Decimal("1") if years-whole>=Decimal("0.5") else Decimal("0"))
    if gratuity.get("enabled") and years>=Decimal(str(gratuity["minimum_service_years"])):
        amount=money(Decimal(str(monthly_basic))*Decimal(str(gratuity["days_per_service_year"]))*years/Decimal(str(gratuity["divisor"])))
        if gratuity.get("maximum_amount") is not None: amount=min(amount,money(gratuity["maximum_amount"]))
        if amount: earnings.append({"type":"gratuity","amount":str(amount),"basis":"approved policy; service years and basic wage"})
    leave_rule=config.get("leave_encashment",{})
    if leave_rule.get("enabled"):
        eligible=set(leave_rule.get("leave_types",[]))
        days=sum((Decimal(str(v)) for k,v in leave_balances.items() if not eligible or k in eligible),Decimal("0"))
        amount=money(days*Decimal(str(monthly_basic if leave_rule.get("wage_basis","basic")=="basic" else monthly_gross))/Decimal(str(leave_rule["divisor"])))
        if amount: earnings.append({"type":"leave_encashment","amount":str(amount),"leave_days":str(days)})
    notice=config.get("notice_pay",{})
    if notice.get("enabled") and notice_days_unserved:
        amount=money(daily*Decimal(str(notice_days_unserved)))
        if amount:
            target=earnings if notice["treatment"]=="earning" else deductions
            target.append({"type":"notice_pay" if target is earnings else "notice_pay_recovery","amount":str(amount),"unserved_days":int(notice_days_unserved)})
    for loan in loan_balances:
        amount=money(loan["outstanding_amount"])
        if amount: deductions.append({"type":"employee_loan_recovery","loan_id":loan["id"],"loan_reference":loan["loan_reference"],"amount":str(amount)})
    earning_total=money(sum((Decimal(x["amount"]) for x in earnings),Decimal("0")))
    statutory=[]
    gross_basis=earning_total
    for rule in config.get("statutory_deductions",[]):
        base=Decimal("0") if rule.get("basis","gross")=="gross" else sum(
            (Decimal(x["amount"]) for x in earnings if x["type"]==rule["basis"]),Decimal("0"))
        if rule.get("basis","gross")=="gross": base=gross_basis
        amount=money(base*Decimal(str(rule.get("rate_percent",0)))/Decimal("100")+Decimal(str(rule.get("fixed_amount",0))))
        if rule.get("maximum_amount") is not None: amount=min(amount,money(rule["maximum_amount"]))
        if amount: statutory.append({"type":str(rule["name"]),"amount":str(amount),"basis":rule.get("basis","gross"),"rate_percent":str(rule.get("rate_percent",0))})
    deductions.extend(statutory)
    deduction_total=money(sum((Decimal(x["amount"]) for x in deductions),Decimal("0")))
    return {"gross_due":str(earning_total),"deductions":str(deduction_total),"net_due":str(money(earning_total-deduction_total)),
            "earnings_breakdown":earnings,"deductions_breakdown":deductions,
            "calculation_basis":{"daily_wage":str(money(daily)),"service_years":str(service_years),
              "leave_balances":{k:str(v) for k,v in leave_balances.items()},"loan_balances":[dict(x) for x in loan_balances]}}
