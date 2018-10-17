import yaml
import datetime


def main():
    now = datetime.datetime.now()
    print now.strftime("%Y-%m-%d")
    exit(0)
    with open('data.yml', 'r') as f:
        doc = yaml.load(f)

    for i in doc:
        if 'Case Was Received' not in i['Status']:
            print i


if __name__ == "__main__":
    main()
