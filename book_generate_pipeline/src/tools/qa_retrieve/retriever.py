import logging
from typing import List, Dict
import dotenv
from .opensearch import OpenSearchClient

dotenv.load_dotenv(override=True)

logger = logging.getLogger(__name__)


class QARetriever:
    """
    QA pair retriever for searching related problems in the QA pair database
    """
    
    def __init__(self):
        """
        Initialize retriever with OpenSearchClient
        """
        self.opensearch_client = OpenSearchClient()
        self.search_func = self.opensearch_client.init_search()
        self.mget_func = self.opensearch_client.init_mget()
        logger.info("QARetriever initialized with OpenSearchClient")
    
    async def search_relevant_problems(
        self,
        query: str,
        variations: List[str] = None,
        fields: List[str] = None,
        exclude_fields: List[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> List[Dict]:
        """
        Search for relevant problems using OpenSearchClient from opensearch.py
        """
        if variations is None:
            variations = []
        if fields is None:
            fields = ["problem", "problem_thumbnail"]
        if exclude_fields is None:
            exclude_fields = ['topic_name', 'solutions']
        
        try:
            logger.info(f"Searching for relevant problems: query='{query}', variations={variations}, fields={fields}")
            
            response = await self.search_func(
                query=query,
                variations=variations,
                fields=fields,
                exclude_fields=exclude_fields,
                page=page,
                page_size=page_size
            )
            
            if response is None:
                logger.warning(f"Search for relevant problems '{query}' returned None")
                return []
            
            problems = []
            for hit in response.get('hits', {}).get('hits', []):
                problem = hit.get('_source', {})
                problems.append({
                    '_id': hit.get('_id', ''),
                    'problem': problem.get('problem', ''),
                    'problem_thumbnail': problem.get('problem_thumbnail', '')
                })
            
            logger.info(f"Found {len(problems)} relevant problems (problem and ID only)")
            return problems
            
        except Exception as e:
            logger.error(f"Error searching for relevant problems '{query}': {e}", exc_info=True)
            return []
    
    async def get_problem_details(self, problem_ids: List[str]) -> List[Dict]:
        """
        Get detailed information based on problem ID list using OpenSearchClient from opensearch.py
        """
        if problem_ids is None or problem_ids == []:
            logger.warning("Problem ID list is empty")
            return []
        
        try:
            logger.info(f"Getting details for {len(problem_ids)} problems using OpenSearchClient mget")
            
            body = {"ids": problem_ids}
            
            response = await self.mget_func(body=body)
            
            if response is None:
                logger.warning("Getting problem details returned None")
                return []
            
            problems = []
            for doc in response.get('docs', []):
                if doc.get('found', False):
                    problem = doc.get('_source', {})
                    problem['_id'] = doc.get('_id')
                    problems.append(problem)
                else:
                    logger.warning(f"Problem {doc.get('_id')} not found")
            
            logger.info(f"Successfully retrieved details for {len(problems)} problems")
            return problems
            
        except Exception as e:
            logger.error(f"Error getting problem details: {e}", exc_info=True)
            return []
    
    async def search_problems_only(
        self,
        query: str,
        variations: List[str] = None,
        max_results: int = 10
    ) -> List[Dict]:
        """
        Search for relevant problems (problem and ID only, no solutions)
        """
        if variations is None:
            variations = []
        
        problems = await self.search_relevant_problems(
            query=query,
            variations=variations,
            page=1,
            page_size=max_results
        )
        
        return problems

