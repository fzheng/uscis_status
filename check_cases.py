import re
import pycurl
import cStringIO
import argparse
import json
import yaml
import datetime
import time
import multiprocessing
import certifi
from multiprocessing import Lock, Manager
from bs4 import BeautifulSoup

CPU_CORES = multiprocessing.cpu_count()
USCIS_URL = "https://egov.uscis.gov/casestatus/mycasestatus.do"


def cmd_args_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--batch", required=True, type=int, help="Batch Number")
    parser.add_argument("-c", "--case_num", required=True, type=str, help="Case Number")
    parser.add_argument("-t", "--case_type_filter", required=False, type=str, help="Case Type Filter")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode will print out more information")
    parser.add_argument("--dryrun", action="store_true", help="dryrun")
    return parser.parse_args()


def get_result(case_num, prefix, case_type_filter, verbose):
    info = {}
    result = ""
    buf = cStringIO.StringIO()
    case_num = prefix + str(case_num)
    c = pycurl.Curl()
    c.setopt(c.URL, USCIS_URL)
    c.setopt(c.POSTFIELDS, "appReceiptNum=%s" % case_num)
    c.setopt(c.WRITEFUNCTION, buf.write)
    c.setopt(c.CAINFO, certifi.where())
    c.perform()

    soup = BeautifulSoup(buf.getvalue(), "html.parser")
    my_case_txt = soup.findAll("div", {"class": "rows text-center"})

    for i in my_case_txt:
        result = result + i.text

    result = result.split("\n")
    buf.close()
    try:
        details = result[2].split(",")
        rcv_date = get_rcv_date(details)
        case_type = get_case_type(result[2])
        if case_type_filter is None or case_type == case_type_filter:
            info[case_num] = {}
            info[case_num]["Queried"] = datetime.datetime.now().isoformat()
            info[case_num]["Type"] = case_type
            info[case_num]["Status"] = result[1]
            info[case_num]["Received"] = rcv_date

        if verbose:
            print info

    except Exception as e:
        print "Invalid USCIS status"

    return info


def get_batch_pair(total_num, case_s, case_e):
    info = []
    for i in range(total_num / CPU_CORES):
        s = CPU_CORES * i + case_s
        e = s + CPU_CORES - 1
        batch = {
            "start": s,
            "end": e
        }
        info.append(batch)
    return info


def query_website(ns, batch_result, prefix, case_type_filter, lock, verbose):
    local_result = []
    if verbose:
        print "s is %d, e is %d" % (int(batch_result["start"]), int(batch_result["end"]))
    for case_n in range(int(batch_result["start"]), int(batch_result["end"])):
        result = get_result(case_n, prefix, case_type_filter, verbose)
        if bool(result):
            local_result.append(result)

    lock.acquire()
    ns.df = ns.df + local_result
    lock.release()
    time.sleep(1)


def get_case_type(line):
    i_case = re.search("\w*I-\w*", line)
    cr_case = re.search("\w*CR-\w*", line)
    ir_case = re.search("\w*IR-\w*", line)

    if i_case:
        return i_case.group(0)
    if cr_case:
        return cr_case.group(0)
    if ir_case:
        return ir_case.group(0)
    return "Unrecognized Case"


def get_rcv_date(details):
    year = str(details[1][1:])

    if year.isdigit():
        date_list = details[0].split(" ")[-2:]
        date_list.append(year)
        rcv_date = " ".join(date_list)
    else:
        rcv_date = None

    return rcv_date


def main():
    final_result = []
    args = cmd_args_parser()
    case_id = int(args.case_num[3:])
    prefix = args.case_num[:3]
    case_type_filter = None
    if hasattr(args, "case_type_filter"):
        case_type_filter = args.case_type_filter
    lock = Lock()
    jobs = []
    mgr = Manager()
    ns = mgr.Namespace()
    ns.df = final_result

    start = case_id - args.batch
    end = case_id + args.batch

    total_num = end - start + 1

    if total_num > 20:
        batch_result = get_batch_pair(total_num, start, end)

        for i in range(len(batch_result)):
            p = multiprocessing.Process(target=query_website, args=(ns, batch_result[i], prefix, case_type_filter, lock, args.verbose,))
            jobs.append(p)
            p.start()
        for job in jobs:
            job.join()

        final_result = ns.df

    else:
        for i in range(start, end):
            result = get_result(i, prefix, case_type_filter, args.verbose)
            if bool(result):
                final_result.append(result)

    json_type = json.dumps(final_result, indent=4)
    now = datetime.datetime.now()
    with open("data-%s.yml" % now.strftime("%Y-%m-%d"), "w") as outfile:
        yaml.dump(yaml.load(json_type), outfile, allow_unicode=True)
    print yaml.dump(yaml.load(json_type), allow_unicode=True, width=256)


if __name__ == "__main__":
    main()
