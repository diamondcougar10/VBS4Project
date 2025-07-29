# Note: this is the standard import script, but ignores "very small" obj files that are sometimes
# found in the wild.  These very small files have no geoemetry and cause the importer to fail and
# your TML gets garbage collected.  Not good.

# This script recursively searches through a folder structure and imports all the models it finds.

# Taken from http://stackoverflow.com/questions/429386/tcl-recursively-search-subdirectories-to-source-all-tcl-files
# findFiles
# basedir - the directory to start looking in
# pattern - A pattern, as defined by the glob command, that the files must match
proc findFiles { basedir pattern } {

    # Fix the directory name, this ensures the directory name is in the
    # native format for the platform and contains a final directory seperator
    set basedir [string trimright [file join [file normalize $basedir] { }]]
    set fileList {}
    # Look in the current directory for matching files, -type {f r}
    # means ony readable normal files are looked at, -nocomplain stops
    # an error being thrown if the returned list is empty
    foreach fileName [glob -nocomplain -type {f r} -path $basedir $pattern] {
        lappend fileList $fileName
    }

    # Now look for any sub direcories in the current directory
    foreach dirName [glob -nocomplain -type {d  r} -path $basedir *] {
        # Recusively call the routine on the sub directory and append any
        # new files to the results
        set subDirList [findFiles $dirName $pattern]
        if { [llength $subDirList] > 0 } {
            foreach subDirFile $subDirList {
                lappend fileList $subDirFile
            }
        }
    }
    return $fileList
 }

#Defines
set extensions [list obj glb gltf]
set Dir $sourceDir

# Open input file.
tsa_open tml [lindex $argv 0]

#Acutally import the models 
foreach ext $extensions {
	# use a recursive search function to obtain all the test model file locations
	set model_filenames [findFiles $Dir *.${ext}]	
	# import each model
	foreach mFile $model_filenames {
		# file tail removes all the path from the string leaving "file.ext"
		set filename [file tail $mFile]
		# sorry for the magic number.... don't import really really tiny files.
		if {[file size $mFile] > 200} {				
			# file rootname removes the final ".ext", leaving "file"
			set modelname [file rootname $filename]
			tml import_model $mFile $modelname -useOriginalTextures
		} else {
			puts stderr "Removing very small file with name: $mFile"
		}
	}		
}




# Save to output file.
tml save [lindex $argv 1]

