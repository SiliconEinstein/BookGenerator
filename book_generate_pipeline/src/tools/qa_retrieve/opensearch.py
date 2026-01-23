from opensearch_dsl import Q, Search
from typing import List
import dotenv
import os
import asyncio
import json
from opensearchpy import OpenSearch
from opensearchpy.connection import Urllib3HttpConnection

dotenv.load_dotenv(override=True) 

class OpenSearchClient:
    def __init__(self):
        self.base_url = os.getenv("OPENSEARCH_HOST") 
        self.username = os.getenv("OPENSEARCH_USERNAME")
        self.password = os.getenv("OPENSEARCH_PASSWORD")
        self.auth = (self.username, self.password)
        self.index = "problems"

        self.opensearch_client = OpenSearch(
            hosts=[
                {
                    'host': self.base_url,
                    'port': 9200,
                }
            ],
            scheme="https",
            http_auth=self.auth,
            use_ssl=True,
            verify_certs=False,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
            connection_class=Urllib3HttpConnection,
            timeout=300,
            # Pool-specific parameters
            pool_maxsize=100,
            maxsize=100,
            block=False,
        )


    def match_phrase_query(self, query, field, slop=None):
        n_words = len(query.split(" "))
        slop = max(n_words - 2, 3) if slop is None else slop
        params = {
            "_name": f"match_phrase_{field}",
            "query": query,
            "slop": slop,
        }
        return Q("match_phrase", **{field: params})
    
    def fuzzy_match_query(self, query, field, fuzziness=None, boost=0.2):
        fuzziness = "AUTO" if fuzziness is None else fuzziness
        params = {
            "_name": f"fuzzy_match_{field}",
            "query": query,
            "operator": "and",
            "fuzziness": fuzziness,
            "boost": boost,
        }
        return Q("match", **{field: params})
    

    def init_search(self):
        async def search_opensearch(query: str, variations: List[str], fields: List, exclude_fields: List[str] = [], page: int = 1, page_size: int = 10):
            s = Search()

            q = Q('bool')
            for field in fields:
                for variation in variations:
                    q = q | self.match_phrase_query(variation, field)
                q = q | self.fuzzy_match_query(query, field)
            if exclude_fields is not None and len(exclude_fields) > 0:
                q = q & ~Q('bool', should=[Q('match_phrase', **{field: query}) for field in exclude_fields])
            q.minimum_should_match = 1

            s = s.query(q)
            s = s.extra(size=page_size, from_=page_size * (page - 1))
            try:
                response = self.opensearch_client.search(index=self.index, body=s.to_dict())
                return response
            except Exception as e:
                print(f"Error searching: {e}")
                return None
        return search_opensearch


    def init_mget(self):
        async def mget_opensearch(body: dict):
            try:
                response = self.opensearch_client.mget(index=self.index, body=body)
                return response
            except Exception as e:
                print(f"Error mget: {e}")
                return None
        return mget_opensearch
    
    def init_search_by_topic(self):
        async def search_opensearch_by_topic(query: str, page: int = 1, page_size: int = 500):
            s = Search()

            q = Q('bool')
            q = q | self.match_phrase_query(query, "topic_name")
            q = q | self.fuzzy_match_query(query, "topic_name")
            q.minimum_should_match = 1

            s = s.query(q)
            s = s.extra(size=page_size, from_=page_size * (page - 1))
            try:
                response = self.opensearch_client.search(index=self.index, body=s.to_dict())
                return response
            except Exception as e:
                print(f"Error searching by topic: {e}")
                return None
        return search_opensearch_by_topic
    
    def init_get_all_fields(self):
        async def get_all_fields():
            dsl_query = {
                "size": 0,
                "aggs": {
                    "unique_values_agg": {
                        "terms": {
                            "field": "field_name.keyword",
                            "size": 500  
                        }
                    }
                }
            }
            try:
                response = self.opensearch_client.search(index=self.index, body=dsl_query)
                if 'aggregations' in response:
                    return response['aggregations']['unique_values_agg']['buckets']
                else:
                    print(response)
                    print("No aggregations found in response or request failed")
                    return []
            except Exception as e:
                print(f"Error getting all fields: {e}")
                return None
        return get_all_fields

    def init_get_all_topics(self):
        async def get_all_topics(field_name: str):
            dsl_query = {
                "size": 0,
                "query": {
                    "bool": {
                        "filter": [
                            {
                                "term": {
                                    "field_name.keyword": field_name
                                }
                            }
                        ]
                    }
                },
                "aggs": {
                    "unique_values_agg": {
                        "terms": {
                            "field": "topic_name.keyword",
                            "size": 500  
                        }
                    }
                }
            }
            try:
                response = self.opensearch_client.search(index=self.index, body=dsl_query)
                if 'aggregations' in response:
                    return response['aggregations']['unique_values_agg']['buckets']
                else:
                    print(response)
                    print("No aggregations found in response or request failed")
                    return []
            except Exception as e:
                print(f"Error getting all topics: {e}")
                return None
        return get_all_topics
    

if __name__ == "__main__":
    openapi_client = OpenSearchClient()

    search_opensearch_by_topic = openapi_client.init_search_by_topic()
    response = asyncio.run(search_opensearch_by_topic(
        "small argument behavior of Bessel function",
        1,
        1
    ))
    print(json.dumps(response, indent=4))
