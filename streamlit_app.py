# Import necessary libraries
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
from urllib.parse import urlparse
import os

# Streamlit app title
st.title("Sitemap Report Generator")

# Function to parse sitemap or sitemap index URL
def fetch_sitemap(url):
    response = requests.get(url)
    if response.status_code == 200:
        tree = ET.ElementTree(ET.fromstring(response.content))
        root = tree.getroot()
        
        # Check if it's an index sitemap by looking for <sitemap> elements
        is_index_sitemap = root.tag == '{http://www.sitemaps.org/schemas/sitemap/0.9}sitemapindex'
        
        if is_index_sitemap:
            sitemaps = []
            # Parse all <sitemap> elements and recursively fetch referenced sitemaps
            for sitemap in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
                loc = sitemap.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
                # Recursively fetch and parse each referenced sitemap
                sub_sitemap = fetch_sitemap(loc)
                if sub_sitemap is not None:
                    sitemaps.extend(sub_sitemap)  # Append the results from sub-sitemaps
            return sitemaps
        else:
            # If it's a regular sitemap, return it as a list containing a single tree
            return [tree]
    else:
        st.error(f"Failed to retrieve sitemap: {response.status_code}")
        return None

# Function to extract URLs and last modified dates from sitemap
def parse_sitemap(sitemap):
    urls = []
    for url in sitemap.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
        loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
        lastmod = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod')
        if lastmod is not None:
            lastmod = lastmod.text
        else:
            lastmod = None  # Handle missing lastmod
        urls.append({'url': loc, 'lastmod': lastmod})
    return pd.DataFrame(urls)

# Function to extract year, subfolders, domain, and file extensions from URLs
def extract_url_info(df):
    # Ensure proper datetime conversion with utc=True
    df['lastmod'] = pd.to_datetime(df['lastmod'], errors='coerce', utc=True).dt.tz_localize(None)
    df['year'] = df['lastmod'].dt.year

    # Extract file extension (if missing, consider as 'html')
    df['file_extension'] = df['url'].apply(lambda x: os.path.splitext(urlparse(x).path)[1][1:] if os.path.splitext(urlparse(x).path)[1] else 'html')

    # Handle first subfolder
    def get_first_subfolder(url):
        split_url = urlparse(url).path.strip('/').split('/')
        # Check if there's at least one folder before the file, otherwise use the file extension
        if len(split_url) > 1 and not os.path.splitext(split_url[-1])[1]:
            return split_url[0]  # Return the first folder
        elif len(split_url) > 1 and os.path.splitext(split_url[-1])[1]:
            return split_url[0]  # Return the first folder if a file exists
        else:
            return f"{os.path.splitext(split_url[-1])[1][1:]}-Dateiendung"  # No folder but a file

    df['first_subfolder'] = df['url'].apply(lambda x: get_first_subfolder(x))

    # Handle second subfolder
    def get_second_subfolder(url):
        split_url = urlparse(url).path.strip('/').split('/')
        if len(split_url) > 2 and not os.path.splitext(split_url[-1])[1]:
            return split_url[1]  # Return the second folder if it exists
        elif len(split_url) > 2 and os.path.splitext(split_url[-1])[1]:
            return split_url[1]  # Return the second folder even if a file exists
        else:
            return 'none'  # No second folder

    df['second_subfolder'] = df['url'].apply(lambda x: get_second_subfolder(x))

    # Extract domain using urlparse and add it to the DataFrame
    df['domain'] = df['url'].apply(lambda x: urlparse(x).netloc)

    return df

# Function to find and list duplicate URLs
def find_duplicates(df):
    duplicate_urls = df[df.duplicated(['url'], keep=False)].sort_values(by=['url'])
    return duplicate_urls

# Function to display the metrics
def display_metrics(df, nested_sitemaps_count):
    total_urls = len(df)
    total_html_documents = len(df[df['file_extension'] == 'html'])
    html_percentage = (total_html_documents / total_urls) * 100 if total_urls > 0 else 0

    # Display metrics in a row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(label="Total URLs in Sitemap", value=total_urls)
    col2.metric(label="Total nested Sitemaps", value=nested_sitemaps_count)
    col3.metric(label="Total duplicate URLs found", value=st.session_state['total_duplicates'])
    col4.metric(label="Percentage of HTML documents", value=f"{html_percentage:.2f}%")

# Main function to generate report from sitemap URL
def generate_report(sitemap_url):
    sitemaps_data = fetch_sitemap(sitemap_url)
    
    if sitemaps_data:
        nested_sitemaps_count = len(sitemaps_data) if isinstance(sitemaps_data, list) else 0
        
        if isinstance(sitemaps_data, list):
            # If it's a list of multiple sitemaps, concatenate the parsed data
            all_entries = []
            for sitemap_tree in sitemaps_data:
                df = parse_sitemap(sitemap_tree)
                all_entries.append(df)
            df = pd.concat(all_entries, ignore_index=True)
        else:
            # Single sitemap
            df = parse_sitemap(sitemaps_data)

        df = extract_url_info(df)

        # Store the dataframe in session state to preserve it across re-renders
        st.session_state['df'] = df
        st.session_state['nested_sitemaps_count'] = nested_sitemaps_count

        # Find total URLs and percentage of HTML documents
        total_urls = len(df)
        total_html_documents = len(df[df['file_extension'] == 'html'])
        html_percentage = (total_html_documents / total_urls) * 100 if total_urls > 0 else 0

        # Find duplicate URLs
        duplicate_urls = find_duplicates(df)
        st.session_state['total_duplicates'] = len(duplicate_urls)

        # Display metrics in a row
        display_metrics(df, nested_sitemaps_count)

# Sidebar filter for first subfolder
def apply_filters():
    df = st.session_state['df']
    first_folder_filter = st.sidebar.selectbox(
        'Filter by First Folder',
        options=['All'] + df['first_subfolder'].unique().tolist(),
        index=0
    )
    if first_folder_filter != 'All':
        df = df[df['first_subfolder'] == first_folder_filter]
    return df

# Streamlit input field and button outside generate_report
sitemap_url = st.text_input('Enter Sitemap URL', '')

# Button to trigger the report generation
if st.button('Generate Report'):
    if sitemap_url:
        generate_report(sitemap_url)
    else:
        st.error("Please enter a valid sitemap URL")

# If the report has been generated, display the filtered results
if 'df' in st.session_state:
    df_filtered = apply_filters()

    # Display the metrics after filtering
    display_metrics(df_filtered, st.session_state['nested_sitemaps_count'])

    # Check if there are any valid lastmod values before displaying the "URLs per Year" table
    if df_filtered['lastmod'].notna().sum() > 0:
        total_urls_with_lastmod = df_filtered['lastmod'].notna().sum()
        total_urls = len(df_filtered)
        
        # Display how many URLs have lastmod
        st.write(f"{total_urls_with_lastmod} out of {total_urls} URLs have 'lastmod' values.")
        
        # Select period for aggregation
        time_period = st.selectbox(
            'Select time period to group URLs by:',
            options=['Year', 'Month-Year', 'Day']
        )

        # Aggregate data based on the selected time period
        if time_period == 'Year':
            timeline_data = df_filtered.groupby(df_filtered['lastmod'].dt.year).size()
            timeline_data.index = timeline_data.index.astype(int)  # Ensure proper display of years as integers
            st.write("URLs grouped by Year:")
            
        elif time_period == 'Month-Year':
            timeline_data = df_filtered.groupby(df_filtered['lastmod'].dt.to_period('M')).size()
            timeline_data.index = timeline_data.index.astype(str)  # Convert Period objects to strings
            st.write("URLs grouped by Month-Year:")
            
        elif time_period == 'Day':
            timeline_data = df_filtered.groupby(df_filtered['lastmod'].dt.to_period('D')).size()
            timeline_data.index = timeline_data.index.astype(str)  # Convert Period objects to strings
            st.write("URLs grouped by Day:")

        # Display bar chart
        st.bar_chart(timeline_data)
    else:
        st.warning("No 'lastmod' values found in the sitemap.")
        st.write("Explanation: Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam quis risus eget urna mollis ornare vel eu leo. Vestibulum id ligula porta felis euismod semper.")

    # Display URLs per file extension table
    st.write("\nURLs per File Extension:")
    file_extension_data = df_filtered.groupby('file_extension').size().reset_index(name='URL Count').sort_values(by='URL Count', ascending=False)
    st.dataframe(file_extension_data)

    # Display URLs per domain table
    st.write("\nURLs per Domain:")
    domain_data = df_filtered.groupby('domain').size().reset_index(name='URL Count').sort_values(by='URL Count', ascending=False)
    st.dataframe(domain_data)

    # Display full URL info table
    st.write("\nFull URL Info Table (URL, Last mod, First folder, Second folder):")
    full_info_table = df_filtered[['url', 'lastmod', 'first_subfolder', 'second_subfolder']].sort_values(by=['url'])
    st.dataframe(full_info_table)

    # Check for duplicates and display duplicate URLs table
    if st.session_state['total_duplicates'] > 0:
        st.write("Duplicate URLs Found:")
        duplicate_urls = find_duplicates(df_filtered)

        # Create a table with URL and Referenced Sitemap
        duplicate_urls_table = pd.DataFrame({
            'URL': duplicate_urls['url'],
            'Referenced Sitemap': [sitemap_url] * len(duplicate_urls)  # Assuming all duplicates are from the same sitemap
        })

        # Use Streamlit's full-width table display
        st.dataframe(duplicate_urls_table, use_container_width=True)
    else:
        st.success("No duplicate URLs found.")
