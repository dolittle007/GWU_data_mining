#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""

Copyright (c) 2016 by H2o.ai

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

---

gen_gdf_file.py is a script that creates data appropriate for creating a
correlation graph, specifically a .GDF format file for the open source
application Gephi.

To use gen_gdf_file.py set the constants directly below using the following
instructions:

IN_FILE_PATH_STRING - Path to input data file. Path must be readbable by
                      h2o.import_file() and the file at the location must be
                      parsable by h2o.import_file().

OUT_FILE_PATH_STRING - Path to created output .GDF file.

COL_TYPE_DICT - Dictionary of columns names as keys and column types as values.
                Column types must be valid H2OFrame column types. 'enum'
                columns will be encoded into numeric 'real' columns. The
                resulting 'real' columns and any pre-existing 'real' and 'int'
                columns will be used in a Pearson correlation calculation and
                will be considered for outputing to the created .GDF file if
                any two 'real' and 'int' column's absolute pairwise Pearson
                correlation is greater than the CORR_THRESHOLD constant.

SEP_STRING - Delimiter character in the file location specified by
             IN_FILE_PATH_STRING.

NA_STRING_LIST - A list of characters signifying NAs in the file location
                 specified by IN_FILE_PATH_STRING.

REPLACE_CHAR - When 'enum' columns are encoded, new columns are created with
               names like <column name><REPLACE_CHAR><categorical level>.
               REPLACE_CHAR will also be used to replace any potentially
               problematic characters in new variable names.

NUM_LEVELS_THRESHOLD - 'enum' variables with more than NUM_LEVELS_THRESHOLD
                       categorical levels will be ignored by the analysis.

CORR_THRESHOLD - Any 'real' and 'int' columns - parsed or generated by encoding
                - will be used in a Pearson correlation calculation and
                will be considered for outputing to the created .GDF file if
                any two column's pairwise Pearson correlation is greater than
                than CORR_THRESHOLD.

"""

#%% constants

IN_FILE_PATH_STRING = '../../../02_analytical_data_prep/data/loan.csv'
OUT_FILE_PATH_STRING = 'loan.gdf'
COL_TYPE_DICT = {}
SEP_STRING = ','
NA_STRING_LIST = ['']
REPLACE_CHAR = '_'
NUM_LEVELS_THRESHOLD = 25
CORR_THRESHOLD = 0.01
DROP_LIST = ['id']

#%% imports

import h2o
import re

#%%

def write_gdf(corr_frame_df, out_file_path_string=OUT_FILE_PATH_STRING,
              corr_threshold=CORR_THRESHOLD):

    """ Utility function to write GDF format file.

    Args:
        corr_frame_df: Pearson corrlation matrix as Pandas dataframe.
        out_file_path_string: Path to generated GDF format file.
        corr_threshold: Absolute Pearson correlation value above which a
                        pair of columns is written to the file specified by
                        out_file_path_string.

    """

    print ('Writing GDF file ...')

    with open(out_file_path_string, 'w+') as out:

        # write node labels
        out.write('nodedef>name VARCHAR,label VARCHAR\n')
        for i in range(0, corr_frame_df.shape[0]):
            out.write(str(i) + ',' + corr_frame_df.columns[i] + '\n')

        # write edge weights
        out.write('edgedef>node1 VARCHAR,node2 VARCHAR, weight DOUBLE\n')
        for i in range(0, corr_frame_df.shape[0]):
            for j in range(0, corr_frame_df.shape[1]):
                if i > j:
                    ij_ = corr_frame_df.iat[i,j]
                    if ij_ > corr_threshold:
                        out.write(str(i) + ',' + str(j) + ',' + str(ij_) +\
                                  '\n')

    print('Done.')

#%%

def main():

    # start h2o, import file
    h2o.init(max_mem_size='6G')
    raw_frame = h2o.import_file(path=IN_FILE_PATH_STRING,
                                sep=SEP_STRING,
                                col_types=COL_TYPE_DICT,
                                na_strings=NA_STRING_LIST
                                )
    raw_frame = raw_frame.drop(DROP_LIST)

    # characters to be replaced by REPLACE_CHAR
    search_str = re.compile(r'[\/\\;,\s\.\/<>&\!:\"\)\(\*\+\?\|=#@]')

    ### initialize encoding loop vars #########################################

    i = 1 # loop in index, used for progress bar
    new_name_list = [] # list used to check for new var name collisions

    # names of all potential vars to be encoded
    try_name_list = [name for name, type_ in raw_frame.types.items() if type_\
                     not in ['unknown', 'uuid', 'time', 'real', 'int']]

    # final list of names of categorical variables
    # w/ < NUM_LEVELS_THRESHOLD levels
    encode_list = [name for name in try_name_list if\
                   len(raw_frame[name].categories()) < NUM_LEVELS_THRESHOLD]

    ### enconding loop ########################################################

    print('Encoding enums ...')
    for name in encode_list:

        name_prefix = re.sub(search_str, REPLACE_CHAR, name)
        name_prefix = re.sub(r"\'", REPLACE_CHAR, name_prefix) # gets '

        level_list = raw_frame[name].categories()
        for j, level in enumerate(level_list):

            # don't create perfectly correlated pairs from categorical
            # binary vars
            if len(level_list) <= 2 and j > 0:
                    continue
            else:

                level_suffix = re.sub(search_str, REPLACE_CHAR, level)
                level_suffix = re.sub(r"\'", REPLACE_CHAR, level_suffix) # '
                new_name = REPLACE_CHAR.join([name_prefix, level_suffix])
                # remedy any name collisions
                while(new_name in new_name_list):
                    new_name += REPLACE_CHAR
                new_name_list.append(new_name)
                new_frame = raw_frame[name].ascharacter()       # ceorce to char
                new_frame.columns = [new_name]                  # new name
                new_frame[new_frame[new_name] == level] = '1.0' # positive condition
                new_frame[new_frame[new_name] != 1.0] = '-1.0'  # negative condition
                new_frame = new_frame.asnumeric()               # coerce to num
                raw_frame = raw_frame.cbind(new_frame)          # add to original frame

        # drop original categorial column
        raw_frame = raw_frame.drop(name)

        i += 1

    print('Done.')

    ### create correlation matrix ############################################
    input_list = [name for name, type_ in raw_frame.types.items() if type_\
                   in ['real', 'int']]

    raw_frame[input_list].impute(method='median')

    print('Calculating Pearson correlations ...')
    corr_frame = raw_frame[input_list].cor()
    print('Done.')

    ### create ouput ##########################################################

    # convert to pandas df to leverage fast iat
    write_gdf(corr_frame.as_data_frame())

    # shutdown h2o
    h2o.cluster().shutdown()

if __name__ == '__main__':
    main()

#%%
