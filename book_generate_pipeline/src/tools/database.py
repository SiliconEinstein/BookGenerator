from typing import Any, Dict, Optional, List
from decimal import Decimal
from mysql.connector import pooling
from mysql.connector import Error
import logging
import dotenv
import os
import asyncio
from typing import Dict

logger = logging.getLogger(__name__)
dotenv.load_dotenv()

ARTICLE_TABLE = 'articles'
WIKI_INDEX_TABLE = 'wiki_index'
REVISIONS_TABLE = 'revisions'
WIKI_MYSQL_DB_HOST='rm-8vb8hf2jdo1359k1geo.mysql.zhangbei.rds.aliyuncs.com'
WIKI_MYSQL_DB_USER='bohr_prod'
WIKI_MYSQL_DB_PASSWORD='5C5d56FfYbJTO0GG'
WIKI_MYSQL_DB_NAME='prod_wiki'
class DatabaseManager:
    """
    A manager for database operations.
    """

    def __init__(self, llm_config):
        try:
            self.pool = pooling.MySQLConnectionPool(
                pool_name="science_knowledge_base_pool",
                pool_size=5,
                host=WIKI_MYSQL_DB_HOST,
                user=WIKI_MYSQL_DB_USER,
                password=WIKI_MYSQL_DB_PASSWORD,
                database=WIKI_MYSQL_DB_NAME,
                charset='utf8mb4',
            )
        except Error as error:
            logger.error("Error creating database connection pool: %s", error)
            self.pool = None
        self.llm_config = llm_config
    
    def init_get_article_content(self):
        def _fetch_article_content(page_info: Dict[str, str]) -> Optional[Dict[str, List[str]]]:
            if not page_info or page_info.get('page_type') != 'article' or page_info.get('page_id') is None:
                return None
            if self.pool is None:
                return None

            article_id = page_info.get('page_id')

            sql_query = f"""
            SELECT
                a.article_id,
                r.article_name,
                a.language,
                a.audience,
                a.article_type as type,
                r.editor_ids,
                r.seo_title,
                r.seo_description,
                r.seo_keywords,
                r.subject,
                r.difficulty,
                r.scope,
                r.key_points,
                r.key_citation,
                r.main_content,
                r.applications,
                r.appendices,
                r.citations
            FROM {ARTICLE_TABLE} a
            JOIN {REVISIONS_TABLE} r
                ON a.article_id = r.article_id
                AND a.current_revision_id = r.revision_id
            WHERE a.article_id = {article_id}
            """

            try:
                with self.pool.get_connection() as conn:
                    with conn.cursor(dictionary=True) as cur:
                        cur.execute(sql_query)
                        rows = cur.fetchall()
                print(len(rows))
            except (Exception, Error) as error:
                print("Error fetching data:", error)
                return None

            results = {'results': rows}
            return results

        async def database_get_article_content(page_info: Dict[str, str]) -> Optional[Dict[str, List[str]]]:
            return await asyncio.to_thread(_fetch_article_content, page_info)

        return database_get_article_content
    
    def init_get_field_index_content(self):
        def _fetch_field_index(page_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
            if not page_info or page_info.get('page_type') != 'field' or page_info.get('page_id') is None:
                return None
            if self.pool is None:
                return None

            root_node_id = page_info.get('page_id')
            sql_query = f"""
            SELECT
                node_id,
                parent_node_id,
                node_type,
                node_name,
                seo_title,
                article_id
            FROM {WIKI_INDEX_TABLE}
            WHERE root_node_id = {root_node_id} OR node_id = {root_node_id}
            AND language = '{page_info.get('wiki_language', 'zh-CN')}'
            """

            try:
                with self.pool.get_connection() as conn:
                    with conn.cursor(dictionary=True) as cur:
                        cur.execute(sql_query)
                        rows = cur.fetchall()
                        print(f"The total number of nodes are: {len(rows)}")
            except (Exception, Error) as error:
                print("Error fetching data:", error)
                return None

            field_nodes = {row.get('node_id'): row for row in rows if row.get('node_type') == 'field'}
            category_nodes = {row.get('node_id'): row for row in rows if row.get('node_type') == 'category'}
            chapter_nodes = {row.get('node_id'): row for row in rows if row.get('node_type') == 'chapter'}
            topic_nodes = {row.get('node_id'): row for row in rows if row.get('node_type') == 'topic'}
            base_url = os.getenv("BOHRIUM_API_BASE", "https://www.bohrium.com")
            for row in rows:
                parent_node_id = row.get('parent_node_id')
                if parent_node_id in field_nodes:
                    if field_nodes[parent_node_id].get('child_nodes', None) is None:
                        field_nodes[parent_node_id]['child_nodes'] = []
                    field_nodes[parent_node_id]['child_nodes'].append(row)
                elif parent_node_id in category_nodes:
                    if category_nodes[parent_node_id].get('child_nodes', None) is None:
                        category_nodes[parent_node_id]['child_nodes'] = []
                    category_nodes[parent_node_id]['child_nodes'].append(row)
                elif parent_node_id in chapter_nodes:
                    if chapter_nodes[parent_node_id].get('child_nodes', None) is None:
                        chapter_nodes[parent_node_id]['child_nodes'] = []
                    chapter_nodes[parent_node_id]['child_nodes'].append(row)

                if row['node_type'] == 'topic':
                    topic_nodes[row['node_id']]['url'] = f"{base_url}/sciencepedia/{row['seo_title']}/{row['article_id']}"

            return field_nodes

        async def database_get_field_index_content(page_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
            return await asyncio.to_thread(_fetch_field_index, page_info)

        return database_get_field_index_content
    
    def init_get_overall_index_content(self):
        def _fetch_overall_index(page_info: Dict[str, str]) -> Optional[Dict[str, List[str]]]:
            if not page_info or page_info.get('page_type') != 'index':
                return None
            if self.pool is None:
                return None

            sql_query = f"""
            SELECT
                node_id,
                node_name,
                node_type,
                coalesce(seo_title, 'field-detail') as seo_title
            FROM {WIKI_INDEX_TABLE}
            WHERE node_type = 'field'
            AND language = '{page_info.get('wiki_language', 'zh-CN')}'
            """

            try:
                with self.pool.get_connection() as conn:
                    with conn.cursor(dictionary=True) as cur:
                        cur.execute(sql_query)
                        rows = cur.fetchall()
                        print(len(rows))
                base_url = os.getenv("BOHRIUM_API_BASE", "https://www.bohrium.com")
                for row in rows:
                    row['url'] = f"{base_url}/sciencepedia/field/{row['seo_title']}/{row['node_id']}"
            except (Exception, Error) as error:
                print("Error fetching data:", error)
                return None
            return {'results': rows}

        async def database_get_overall_index_content(page_info: Dict[str, str]) -> Optional[Dict[str, List[str]]]:
            return await asyncio.to_thread(_fetch_overall_index, page_info)

        return database_get_overall_index_content
    
    def init_get_page_content(self):
        async def database_get_page_content(page_info: Dict[str, str]) -> Dict[str, List[str]]:
            """
            Get the page content from the database.
            """
            if page_info.get('page_type') == 'article':
                get_article_content = self.init_get_article_content()
                return await get_article_content(page_info)
            elif page_info.get('page_type') == 'field':
                get_field_index_content = self.init_get_field_index_content()
                return await get_field_index_content(page_info)
            elif page_info.get('page_type') == 'index':
                get_overall_index_content = self.init_get_overall_index_content()
                return await get_overall_index_content(page_info)
            else:
                return None
        return database_get_page_content
