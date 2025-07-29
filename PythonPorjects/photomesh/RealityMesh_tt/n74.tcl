set modelDir OneClick_output
set mexExe P:/tools/ModelExchanger/ModelExchangerCmd.exe
set apExe P:/tools/blue/AddonPacker_64/AddonPacker_x64.exe
set vbsBlueVersion blue.trunk
set outputDir E:/VBS4/myData/Blue/content
set tempDir vbs2/customer/structures/$modelDir

file mkdir P:/$tempDir
# Open input file.
brep_open world [lindex $argv 0]

world nodeapply n {
    if {[n hasattr @mref_model]} {
		set modelName [n get @mref_model]
		set args "asset-converter --force --input \"P:/$modelDir/$modelName.glb\" --outputfilename \"$modelName\" --outputtype \"p3d\" --outputdirectory \"P:/$tempDir\" "
		puts "CMD> $mexExe $args"
		exec $mexExe {*}$args
		puts ""
		n set @vbs2_model "[string map {/ \\} $tempDir]\\$modelName.p3d"
		n delattr @mref_model
	}
}

set args " -v $vbsBlueVersion -s -severity debug -ap -ac -r -pfd  -exfi *.dep;*.log;*.pbo;*.ascii -t \"P:/temp\" -ld \"P:/export/$modelDir\" -i \"P:/$tempDir\" -o \"$outputDir\""
puts "CMD> $apExe $args"
exec $apExe {*}$args

# Save to output file.
world save [lindex $argv 1]
