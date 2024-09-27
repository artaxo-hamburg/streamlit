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

# Function to extract URLs, last modified dates, and images from sitemap
def parse_sitemap(sitemap):
    urls = []
    for url in sitemap.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
        loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
        lastmod = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod')
        if lastmod is not None:
            lastmod = lastmod.text
        else:
            lastmod = None  # Handle missing lastmod

        # Extract images
        images = []
        for image in url.findall('{http://www.google.com/schemas/sitemap-image/1.1}image'):
            image_loc = image.find('{http://www.google.com/schemas/sitemap-image/1.1}loc').text
            images.append(image_loc)
        
        # Append URL data including the images
        urls.append({'url': loc, 'lastmod': lastmod, 'images': images})
    
    return pd.DataFrame(urls)

# Function to extract year, subfolders, domain, and file extensions from URLs, including images
def extract_url_info(df):
    # Ensure proper datetime conversion with utc=True
    df['lastmod'] = pd.to_datetime(df['lastmod'], errors='coerce', utc=True).dt.tz_localize(None)
    df['year'] = df['lastmod'].dt.year

    # Extract file extension (if missing, consider as 'html')
    df['file_extension'] = df['url'].apply(lambda x: os.path.splitext(urlparse(x).path)[1][1:] if os.path.splitext(urlparse(x).path)[1] else 'html')

    # Handle first subfolder
    def get_first_subfolder(url):
        split_url = urlparse(url).path.strip('/').split('/')
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

    # Keep the images as a separate column
    df['images'] = df['images'].apply(lambda x: ', '.join(x) if x else None)

    return df

# Function to find and list duplicate URLs and images based on the filter
def find_duplicates(df, file_type_filter):
    if file_type_filter == 'HTML':
        # Find duplicate URLs that are .html files
        duplicate_urls = df[df['file_extension'] == 'html']
        duplicate_urls = duplicate_urls[duplicate_urls.duplicated(['url'], keep=False)].sort_values(by=['url'])
        duplicate_images = pd.DataFrame()  # No image duplicates for HTML filter
    elif file_type_filter == 'Images':
        # Find duplicate images
        all_images = df.explode('images')  # Split the images column into individual rows
        valid_images = all_images[all_images['images'].notna() & (all_images['images'] != '')]
        duplicate_images = valid_images[valid_images.duplicated(['images'], keep=False)].sort_values(by=['images'])
        duplicate_urls = pd.DataFrame()  # No URL duplicates for Images filter
    else:  # file_type_filter == 'All'
        # Find duplicate URLs
        duplicate_urls = df[df.duplicated(['url'], keep=False)].sort_values(by=['url'])
        # Find duplicate images
        all_images = df.explode('images')  # Ensure all images are considered
        valid_images = all_images[all_images['images'].notna() & (all_images['images'] != '')]
        duplicate_images = valid_images[valid_images.duplicated(['images'], keep=False)].sort_values(by=['images'])

    total_duplicates = len(duplicate_urls) + len(duplicate_images)
    return duplicate_urls, duplicate_images, total_duplicates

# Function to display the metrics, dynamically adjusted based on filtered data
def display_metrics(df_filtered, nested_sitemaps_count, file_type_filter):
    total_urls = len(df_filtered)  # Total URLs in the filtered data

    if file_type_filter == 'HTML':
        # Count only URLs with .html file extension
        total_html_documents = len(df_filtered[df_filtered['file_extension'] == 'html'])
        percentage_html = (total_html_documents / total_urls) * 100 if total_urls > 0 else 0.0
        total_images = 0
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(label="Total HTML URLs", value=total_html_documents)
        col4.metric(label="Percentage of HTML documents", value=f"{percentage_html:.2f}%")
    elif file_type_filter == 'Images':
        # Count total number of images in all URLs
        total_images = df_filtered['images'].apply(lambda x: len(x.split(', ')) if x else 0).sum()
        percentage_images = (total_images / total_urls) * 100 if total_urls > 0 else 0.0
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(label="Total Images", value=total_images)
        col4.metric(label="Percentage of Images", value=f"{percentage_images:.2f}%")
    else:  # file_type_filter == 'All'
        # Count all .html URLs and total images combined
        total_html_documents = len(df_filtered[df_filtered['file_extension'] == 'html'])
        total_images = df_filtered['images'].apply(lambda x: len(x.split(', ')) if x else 0).sum()
        total_combined = total_html_documents + total_images
        percentage_html = (total_html_documents / total_combined) * 100 if total_combined > 0 else 0.0
        percentage_images = (total_images / total_combined) * 100 if total_combined > 0 else 0.0
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(label="Total URLs (HTML + Images)", value=total_combined)
        col4.metric(label="Percentage of HTML documents", value=f"{percentage_html:.2f}%")
        col4.metric(label="Percentage of Images", value=f"{percentage_images:.2f}%")

    # Recalculate the duplicates based on the filtered data
    duplicate_urls, duplicate_images, total_duplicates = find_duplicates(df_filtered, file_type_filter)

    # Display metrics for duplicates and nested sitemaps
    col2.metric(label="Total nested Sitemaps", value=nested_sitemaps_count)
    col3.metric(label="Total duplicates", value=total_duplicates)

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

# Sidebar filter for first subfolder and file type (HTML or image)
def apply_filters():
    df = st.session_state['df']
    
    # Filter by first folder
    first_folder_filter = st.sidebar.selectbox(
        'Filter by First Folder',
        options=['All'] + df['first_subfolder'].unique().tolist(),
        index=0
    )
    if first_folder_filter != 'All':
        df = df[df['first_subfolder'] == first_folder_filter]
    
    # Filter by file type (HTML or images)
    file_type_filter = st.sidebar.selectbox(
        'Filter by File Type',
        options=['All', 'HTML', 'Images'],
        index=0
    )
    if file_type_filter == 'HTML':
        df = df[df['file_extension'] == 'html']
    elif file_type_filter == 'Images':
        df = df[df['images'].notna() & (df['images'] != '')]

    return df, file_type_filter

# Streamlit input field and button outside generate_report
sitemap_url = st.text_input('Enter Sitemap URL', '')

# Button to trigger the report generation
if st.button('Generate Report'):
    if sitemap_url:
        generate_report(sitemap_url)
    else:
        st.error("Please enter a valid sitemap URL")

# If the report has been generated, display the filtered results and metrics
if 'df' in st.session_state:
    df_filtered, file_type_filter = apply_filters()

    # Display the metrics after filtering
    display_metrics(df_filtered, st.session_state['nested_sitemaps_count'], file_type_filter)

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

    # Display URLs per file extension table
    st.write("\nURLs per File Extension:")
    file_extension_data = df_filtered.groupby('file_extension').size().reset_index(name='URL Count').sort_values(by='URL Count', ascending=False)
    st.dataframe(file_extension_data)

    # Display URLs per domain table
    st.write("\nURLs per Domain:")
    domain_data = df_filtered.groupby('domain').size().reset_index(name='URL Count').sort_values(by='URL Count', ascending=False)
    st.dataframe(domain_data)

    # Display full URL info table including images
    st.write("\nFull URL Info Table (URL, Last mod, First folder, Second folder, Images):")
    full_info_table = df_filtered[['url', 'lastmod', 'first_subfolder', 'second_subfolder', 'images']].sort_values(by=['url'])

    # Use Streamlit's table display with images
    st.dataframe(full_info_table)

    # Check for duplicates and display duplicate URLs and images tables
    duplicate_urls, duplicate_images, total_duplicates = find_duplicates(df_filtered, file_type_filter)
    
    if total_duplicates > 0 or not duplicate_images.empty:
        st.write("Duplicate URLs and Images Found:")

        # Display duplicate URLs
        if not duplicate_urls.empty:
            st.write("Duplicate URLs:")
            st.dataframe(duplicate_urls[['url']])

        # Display duplicate images
        if not duplicate_images.empty:
            st.write("Duplicate Images:")
            st.dataframe(duplicate_images[['images']])
    else:
        st.success("No duplicate URLs or images found.")
