# Legacy Scrapy pipeline retained for manual crawler use. Daily Actions use collect_arxiv.py.


class DailyArxivPipeline:
    def process_item(self, item: dict, spider):
        return item
